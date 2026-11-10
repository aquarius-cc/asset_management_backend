# 批次5 M-45 批A：string_utils 收敛——5/6 函数生产零引用删除，仅保留唯一存活的
# mask_phone_number（core/audit_sanitizer.py 审计脱敏链唯一消费，见 rg 实证）。
# generate_random_string / generate_numeric_code / generate_token / mask_sensitive_info /
# mask_id_card 删除依据：merge-audit-20261107 M-45①②（全仓剔除自身后零外部调用）。


def mask_phone_number(phone: str) -> str:
    """
    脱敏手机号

    专门用于手机号脱敏,固定格式为前3位+****+后4位。

    Args:
        phone: 手机号字符串

    Returns:
        str: 脱敏后的手机号

    Example:
        >>> mask_phone_number('13812345678')
        '138****5678'
    """
    if not phone:
        return ""
    if len(phone) <= 3 + 4:
        return "*" * len(phone)
    return phone[:3] + "*" * (len(phone) - 7) + phone[-4:]
