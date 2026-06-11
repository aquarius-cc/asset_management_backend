"""
字符串工具函数

提供项目中常用的字符串处理函数，包括随机字符串生成、敏感信息脱敏等功能。
"""
import string
import secrets
from typing import Optional


def generate_random_string(length: int = 8, chars: Optional[str] = None) -> str:
    """
    生成密码安全的随机字符串

    【修复 S6】使用 secrets 模块替代 random 模块，确保随机数不可预测。
    适用于生成密码重置 token、验证码、API key 等安全相关字符串。

    Args:
        length: 字符串长度，默认 8 位
        chars: 可选字符集，默认使用字母+数字

    Returns:
        str: 生成的随机字符串

    Example:
        >>> generate_random_string(16)
        'aK9mX2pL7qR4sT6'
    """
    if chars is None:
        chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


def generate_numeric_code(length: int = 6) -> str:
    """
    生成纯数字随机码

    适用于短信验证码、支付密码等纯数字场景。

    Args:
        length: 码长度，默认 6 位

    Returns:
        str: 生成的纯数字随机码

    Example:
        >>> generate_numeric_code(4)
        '3847'
    """
    return ''.join(secrets.choice(string.digits) for _ in range(length))


def generate_token(length: int = 32) -> str:
    """
    生成 URL 安全的随机 token

    使用 secrets.token_urlsafe 生成符合 URL 安全要求的随机 token。
    适用于 API token、session id 等场景。

    Args:
        length: token 长度（字节数），默认 32 字节

    Returns:
        str: 生成的 URL 安全 token

    Example:
        >>> generate_token(16)
        'WcM3zX9kPqR2vN5...'
    """
    return secrets.token_urlsafe(length)


def mask_sensitive_info(info: str, start: int = 3, end: int = 4) -> str:
    """
    脱敏敏感信息

    将字符串的中间部分替换为星号，常用于手机号、身份证号、银行卡号等。

    【修复 S6】增强对短字符串的处理，避免完全暴露。

    Args:
        info: 原始信息字符串
        start: 开头保留字符数，默认 3
        end: 结尾保留字符数，默认 4

    Returns:
        str: 脱敏后的字符串

    Example:
        >>> mask_sensitive_info('13812345678')
        '138****5678'
        >>> mask_sensitive_info('13812345678', start=2, end=2)
        '13****678'
    """
    if not info or len(info) <= start + end:
        # 【修复 S6】对于短字符串，全部脱敏
        return '*' * len(info) if info else ''

    return info[:start] + '*' * (len(info) - start - end) + info[-end:]


def mask_phone_number(phone: str) -> str:
    """
    脱敏手机号

    专门用于手机号脱敏，固定格式为前3位+****+后4位。

    Args:
        phone: 手机号字符串

    Returns:
        str: 脱敏后的手机号

    Example:
        >>> mask_phone_number('13812345678')
        '138****5678'
    """
    return mask_sensitive_info(phone, start=3, end=4)


def mask_id_card(id_card: str) -> str:
    """
    脱敏身份证号

    专门用于身份证号脱敏，固定格式为前6位+********+后4位。

    Args:
        id_card: 身份证号字符串

    Returns:
        str: 脱敏后的身份证号

    Example:
        >>> mask_id_card('110101199001011234')
        '110101********1234'
    """
    if not id_card or len(id_card) < 14:
        return '*' * len(id_card) if id_card else ''
    return id_card[:6] + '*' * 8 + id_card[-4:]
