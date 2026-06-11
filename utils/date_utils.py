# d:\CodeDemo\Python\asset_management_backend\utils\date_utils.py
"""
日期工具函数
"""

from datetime import datetime, timedelta, date
from typing import Tuple, Optional


def format_date(
    date_obj: Optional[datetime.date],
    format_str: str = '%Y-%m-%d'
) -> Optional[str]:
    """
    格式化日期对象为字符串
    
    Args:
        date_obj: 日期对象
        format_str: 格式化字符串
        
    Returns:
        格式化后的日期字符串
    """
    if date_obj is None:
        return None
    
    if isinstance(date_obj, datetime):
        return date_obj.strftime(format_str)
    elif isinstance(date_obj, date):
        return date_obj.strftime(format_str)
    return str(date_obj)


def parse_date(
    date_str: str,
    format_str: str = '%Y-%m-%d'
) -> Optional[date]:
    """
    解析日期字符串为日期对象
    
    Args:
        date_str: 日期字符串
        format_str: 格式化字符串
        
    Returns:
        日期对象
    """
    if not date_str:
        return None
    
    try:
        return datetime.strptime(date_str, format_str).date()
    except (ValueError, TypeError):
        return None


def get_date_range(
    start_date: date,
    end_date: date
) -> list:
    """
    获取日期范围内的所有日期
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
        
    Returns:
        日期列表
    """
    delta = end_date - start_date
    return [start_date + timedelta(days=i) for i in range(delta.days + 1)]


def get_week_start_end(
    target_date: Optional[date] = None
) -> Tuple[date, date]:
    """
    获取指定日期所在周的开始和结束日期
    
    Args:
        target_date: 目标日期，默认今天
        
    Returns:
        (周一开始, 周日结束)
    """
    if target_date is None:
        target_date = date.today()
    
    # 周一为一周的开始
    start = target_date - timedelta(days=target_date.weekday())
    end = start + timedelta(days=6)
    
    return start, end


def get_month_start_end(
    year: int,
    month: int
) -> Tuple[date, date]:
    """
    获取指定月份的开始和结束日期
    
    Args:
        year: 年份
        month: 月份
        
    Returns:
        (月份开始, 月份结束)
    """
    # 月份开始
    start = date(year, month, 1)
    
    # 月份结束（下一月第一天减一天）
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    
    return start, end