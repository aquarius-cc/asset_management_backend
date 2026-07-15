# d:\CodeDemo\Python\asset_management_backend\core\validators.py
"""
自定义验证器

提供项目统一的数据验证功能：
- validate_asset_code: 验证资产编码格式
- validate_phone_number: 验证手机号码格式
- validate_id_card: 验证身份证号码格式
- validate_positive_number: 验证正数
"""

import re

from django.core.exceptions import ValidationError as DjangoValidationError


def validate_asset_code(value: str) -> str:
    """
    验证资产编码格式

    格式要求：字母开头，后面可以是字母、数字、下划线。
    
    Args:
        value: 资产编码字符串
        
    Returns:
        验证通过的资产编码
        
    Raises:
        DjangoValidationError: 格式不正确时抛出
    """
    pattern = r'^[A-Za-z][A-Za-z0-9_]*$'
    if not re.match(pattern, value):
        raise DjangoValidationError(
            '资产编码格式不正确，应以字母开头，可包含字母、数字和下划线'
        )
    return value


def validate_phone_number(value: str) -> str:
    """
    验证手机号码格式（中国大陆）

    格式要求：11位数字，以1开头，第二位为3-9。
    
    Args:
        value: 手机号码字符串
        
    Returns:
        验证通过的手机号码
        
    Raises:
        DjangoValidationError: 格式不正确时抛出
    """
    pattern = r'^1[3-9]\d{9}$'
    if not re.match(pattern, value):
        raise DjangoValidationError('手机号码格式不正确')
    return value


def validate_id_card(value: str) -> str:
    """
    验证身份证号码格式（中国大陆）

    格式要求：18位，包含数字和最后一位可能为X。
    
    Args:
        value: 身份证号码字符串
        
    Returns:
        验证通过的身份证号码
        
    Raises:
        DjangoValidationError: 格式不正确时抛出
    """
    pattern = r'^[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]$'
    if not re.match(pattern, value):
        raise DjangoValidationError('身份证号码格式不正确')
    return value


def validate_non_negative_number(value: int) -> int:
    """
    【P2-32 修复】重命名：validate_positive_number → validate_non_negative_number
    确保数值大于等于0（允许零值）。
    
    Args:
        value: 待验证的数值
        
    Returns:
        验证通过的数值
        
    Raises:
        DjangoValidationError: 数值为负数时抛出
    """
    if value < 0:
        raise DjangoValidationError('数值不能为负数')
    return value


# 向后兼容别名
validate_positive_number = validate_non_negative_number
