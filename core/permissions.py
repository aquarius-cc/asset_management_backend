# d:\CodeDemo\Python\asset_management_backend\core\permissions.py
"""
自定义权限类

提供项目统一的权限控制：
- IsOwnerOrReadOnly: 资源所有者可修改，其他用户只读（已移除，项目中资源无统一 owner/user 字段）
- IsAdminUser: 仅管理员可访问
- IsAuthenticatedUser: 仅登录用户可访问
"""

from rest_framework import permissions


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    只有资源所有者才能修改，其他用户只能读取

    检查对象是否有 `owner` 或 `user` 字段，并验证当前用户是否为所有者。
    对于安全方法（GET, HEAD, OPTIONS），所有用户都有访问权限。
    
    Example:
        class MyViewSet(viewsets.ModelViewSet):
            permission_classes = [IsOwnerOrReadOnly]
    """

    def has_object_permission(self, request, view, obj):
        """检查对象级权限"""
        # 读取权限允许任何请求
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # 写入权限只有所有者才有
        # 假设模型有 user 或 owner 字段
        if hasattr(obj, 'owner'):
            return obj.owner == request.user
        if hasattr(obj, 'user'):
            return obj.user == request.user
        return False


class IsAdminUser(permissions.BasePermission):
    """
    只有管理员才能访问

    验证用户是否已认证且具有管理员权限（is_staff=True）。
    
    Example:
        class AdminViewSet(viewsets.ModelViewSet):
            permission_classes = [IsAdminUser]
    """

    def has_permission(self, request, view):
        """检查视图级权限"""
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.is_staff
        )


class IsAuthenticatedUser(permissions.BasePermission):
    """
    需要登录才能访问

    验证用户是否已成功认证。
    
    Example:
        class ProtectedViewSet(viewsets.ModelViewSet):
            permission_classes = [IsAuthenticatedUser]
    """

    def has_permission(self, request, view):
        """检查视图级权限"""
        return bool(request.user and request.user.is_authenticated)