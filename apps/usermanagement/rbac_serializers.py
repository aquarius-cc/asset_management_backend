"""
RBAC 序列化器(Role / Permission / UserRole)

提供角色、权限点、用户-角色关联的序列化,独立于 department/employee 序列化器,
避免继续膨胀 serializers.py(532 行,已超 DR-5 存量红线)。

字段契约(与前端类型逐字段对齐):
- Role                    → types/roles.ts Role(含 recordcode/created_at/updated_at)
- RoleCreateUpdate        → types/roles.ts RoleCreateUpdateForm(role_level 1-5,is_system 只读)
- UserRole                → api/authusers.ts UserRole(id/auth_user/role/role_name/role_code/data_scope/created_at)
- Permission              → types/permission.ts Permission(id/permission_code/module/action/description)

写入约定:
- UserRoleSerializer 接收 role_id(write_only, source="role"),与前端 authusers.ts
  assignUserRole 的 {role_id} payload 对齐(D3 决策)。
"""

from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from apps.usermanagement.models import Permission, Role, UserRole


class RoleSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """
    角色基础序列化器(只读输出)

    用于角色列表与详情展示,字段对齐前端 types/roles.ts Role。
    """

    class Meta:
        model = Role
        fields = [
            "id",
            "recordcode",
            "role_code",
            "role_name",
            "role_level",
            "description",
            "is_system",
            "sort_order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class RoleCreateUpdateSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """
    角色创建/更新序列化器

    安全约束:
    - role_code 唯一校验(仅对 is_deleted=False 生效,兼容软删除唯一约束)
    - role_level 限定 1-5(对齐角色层级 5/4/3/2/1)
    - is_system 只读(系统内置角色保护,客户端不可写入)
    """

    role_code = serializers.CharField(
        max_length=50,
        validators=[
            UniqueValidator(
                queryset=Role.objects.filter(is_deleted=False),
                message="该角色编码已存在",
            )
        ],
    )
    role_level = serializers.IntegerField(min_value=1, max_value=5)

    class Meta:
        model = Role
        fields = [
            "id",
            "recordcode",
            "role_code",
            "role_name",
            "role_level",
            "description",
            "is_system",
            "sort_order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "recordcode", "is_system", "created_at", "updated_at"]


class UserRoleSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """
    用户-角色关联序列化器

    输出字段(id/auth_user/role/role_name/role_code/data_scope/created_at)
    对齐前端 api/authusers.ts UserRole。

    写入:
    - role_id: write_only + source="role",兼容前端 {role_id} payload(D3 决策)
    - auth_user: 只读,由嵌套 URL 注入,禁止 body 写入
    - data_scope: 可选,缺省时由 RoleService 继承 Employee 部门(D1 决策)
    """

    role_id = serializers.PrimaryKeyRelatedField(
        source="role",
        queryset=Role.objects.filter(is_deleted=False),
        write_only=True,
        help_text="角色 ID(写入用)",
    )
    role_name = serializers.CharField(source="role.role_name", read_only=True, help_text="角色名称")
    role_code = serializers.CharField(source="role.role_code", read_only=True, help_text="角色编码")
    data_scope = serializers.JSONField(read_only=True, help_text="数据范围(由 Service 按 D1 计算)")

    class Meta:
        model = UserRole
        fields = [
            "id",
            "auth_user",
            "role",
            "role_id",
            "role_name",
            "role_code",
            "data_scope",
            "created_at",
        ]
        read_only_fields = ["id", "auth_user", "role", "created_at"]


class PermissionSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """
    权限点序列化器(只读)

    字段对齐前端 types/permission.ts Permission。
    """

    class Meta:
        model = Permission
        fields = ["id", "permission_code", "module", "action", "description"]
        read_only_fields = fields
