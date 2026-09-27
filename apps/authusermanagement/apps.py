"""
认证与用户管理应用配置
"""

from django.apps import AppConfig


class AuthusermanagementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.authusermanagement"
    verbose_name = "认证与用户管理"

    def ready(self) -> None:
        """导入 OpenAPI 认证扩展，完成注册（BF-051）。

        drf-spectacular 靠 ``__init_subclass__`` 把扩展挂进 ``_registry``，**不做模块
        自动发现**（全库无 import_module / pkgutil 扫描）。扩展模块没被 import 就等于
        没写——``components.securitySchemes`` 会静默缺失、每个使用该认证类的视图还会
        打出 ``could not resolve authenticator`` 告警。故在此显式导入。

        已实测：移除本方法后 ``test_openapi_security_schema`` 的 3 条用例会红，其中
        ``test_no_dangling_security_references`` 会逐条列出全部悬空 operation。
        """
        from . import schema  # noqa: F401
