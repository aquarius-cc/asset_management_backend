"""
自定义节流类

提供项目统一的频率限制:
- RegisterRateThrottle: 注册接口频率限制(5次/分钟)
"""

from rest_framework.throttling import AnonRateThrottle


class RegisterRateThrottle(AnonRateThrottle):
    """
    注册接口频率限制

    使用 scope='register',在 settings 中配置具体频率。
    默认 5次/分钟,防止批量注册攻击。
    """

    scope = "register"
