"""
认证与用户管理Admin配置
"""

from django.contrib import admin

from apps.authusermanagement.models import AuthUser


@admin.register(AuthUser)
class AuthUserAdmin(admin.ModelAdmin):
    """
    自定义用户管理配置
    """

    list_display = (
        "auth_id",
        "auth_username",
        "email",
        "auth_phone",
        "auth_is_active",
        "auth_is_staff",
        "auth_date_create",
    )
    list_filter = ("auth_is_active", "auth_is_staff", "auth_date_create")
    search_fields = ("auth_username", "email", "auth_phone")
    ordering = ("auth_username",)

    fieldsets = (
        (None, {"fields": ("auth_username", "password")}),
        ("个人信息", {"fields": ("email", "auth_phone")}),
        ("权限", {"fields": ("auth_is_active", "auth_is_staff")}),
        ("日期信息", {"fields": ("auth_date_create", "auth_date_update")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("auth_username", "password1", "password2", "auth_phone", "auth_is_active", "auth_is_staff"),
            },
        ),
    )

    readonly_fields = ("auth_date_create", "auth_date_update")
