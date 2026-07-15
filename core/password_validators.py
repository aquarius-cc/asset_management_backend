"""
自定义密码策略校验器

增强 Django 默认密码验证，要求：
- 最少 8 位
- 至少包含大写字母、小写字母、数字、特殊字符中的 3 种
"""


import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class ComplexPasswordValidator:
    """
    密码复杂度校验器
    要求密码至少包含大写、小写、数字、特殊字符中的 3 种。
    """

    def validate(self, password: str, user=None) -> None:
        categories = 0
        if re.search(r"[A-Z]", password):
            categories += 1
        if re.search(r"[a-z]", password):
            categories += 1
        if re.search(r"\d", password):
            categories += 1
        if re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            categories += 1
        if categories < 3:
            raise ValidationError(
                _("密码必须包含大写字母、小写字母、数字、特殊字符中的至少 3 种。"),
                code="password_too_simple",
            )

    def get_help_text(self) -> str:
        return _("密码必须包含大写字母、小写字母、数字、特殊字符中的至少 3 种。")
