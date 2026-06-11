"""
认证与用户管理序列化器

提供用户认证、注册等相关的序列化器
"""
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import AuthUser
from typing import Dict, Any


class AuthUserSerializer(serializers.ModelSerializer):
    """
    认证用户序列化器

    用于用户信息的序列化和反序列化

    【修复 S7】将敏感字段移至 read_only_fields，防止通过 API 修改
    """

    class Meta:
        model = AuthUser
        fields = (
            'auth_id',
            'auth_username',
            'email',
            'auth_is_active',
            'auth_is_staff',
            'auth_phone',
            'auth_date_create',
            'auth_date_update',
            # 'sort_order'  # 【AGENTS规范】暴露排序字段
        )
        read_only_fields = (
            'auth_id',
            'auth_username',
            'auth_is_active',
            'auth_is_staff',
            'auth_date_create',
            'auth_date_update'
        )


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    """
    用户个人信息更新序列化器

    【修复 S7】专用于用户更新自己的个人信息，排除所有敏感字段
    仅允许更新：email, auth_phone
    """
    password = serializers.CharField(
        write_only=True,
        required=False,
        validators=[validate_password],
        style={'input_type': 'password'}
    )

    class Meta:
        model = AuthUser
        fields = ('email', 'auth_phone', 'password')
        # 所有字段都应该是可选的，因为用户可能只想更新其中一个
        extra_kwargs = {
            'email': {'required': False},
            'auth_phone': {'required': False},
        }

    def update(self, instance: AuthUser, validated_data: Dict[str, Any]) -> AuthUser:
        """更新用户个人信息"""
        # 处理密码更新
        if 'password' in validated_data:
            instance.set_password(validated_data['password'])

        # 更新其他字段
        for field in ['email', 'auth_phone']:
            if field in validated_data:
                setattr(instance, field, validated_data[field])

        instance.save()
        return instance


class RegisterSerializer(serializers.ModelSerializer):
    """
    用户注册序列化器

    用于处理用户注册请求的数据验证和创建

    【修复 S8】确保注册接口不能创建管理员，忽略客户端传入的 auth_is_staff
    """

    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={'input_type': 'password'}
    )
    password2 = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )

    class Meta:
        model = AuthUser
        fields = ('auth_username', 'password', 'password2', 'email', 'auth_phone')

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证注册数据

        【修复 S8】确保两次密码输入一致
        """
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "两次输入的密码不一致"})
        # 【修复 S8】移除 password2，避免泄露
        attrs.pop('password2', None)
        return attrs

    def create(self, validated_data: Dict[str, Any]) -> AuthUser:
        """
        创建用户实例

        【修复 S8】强制设置 auth_is_staff=False，不允许注册为管理员
        """
        # 【修复 S8】移除任何可能被注入的敏感字段
        validated_data.pop('auth_is_staff', None)
        validated_data.pop('auth_is_active', None)
        validated_data.pop('is_superuser', None)

        user: AuthUser = AuthUser.objects.create_user(
            auth_username=validated_data['auth_username'],
            password=validated_data['password'],
            email=validated_data.get('email', ''),
            auth_phone=validated_data.get('auth_phone', ''),
            # 【修复 S8】强制为普通用户
            auth_is_staff=False,
            auth_is_active=True,
        )
        return user


class LoginSerializer(serializers.Serializer):
    """
    用户登录序列化器

    用于处理用户登录请求的数据验证
    """

    auth_username = serializers.CharField(required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )

    def validate(self, attrs: Dict[str, str]) -> Dict[str, str]:
        """验证登录数据"""
        if not isinstance(attrs.get('auth_username'), str):
            raise serializers.ValidationError({"auth_username": "用户名必须为字符串"})
        if not isinstance(attrs.get('password'), str):
            raise serializers.ValidationError({"password": "密码必须为字符串"})
        return attrs

class LogoutSerializer(serializers.Serializer):
    """
    用户退出登录序列化器

    用于验证退出登录请求中的 refresh_token，
    客户端必须提供有效的 refresh_token 才能执行退出操作。

    【安全设计】
    - refresh_token 为必填项，确保只有持有有效 refresh_token 的客户端才能执行退出
    - 这防止了恶意用户随意作废他人 Token 的可能
    """
    refresh = serializers.CharField(
        required=True,
        help_text='需要作废的 refresh token'
    )

    def validate_refresh(self, value: str) -> str:
        """
        验证 refresh_token 格式

        Args:
            value: 客户端提交的 refresh_token 字符串

        Returns:
            str: 验证通过的 refresh_token

        Raises:
            serializers.ValidationError: 当 refresh_token 为空字符串时
        """
        if not value or not value.strip():
            raise serializers.ValidationError("refresh_token 不能为空")
        return value.strip()
