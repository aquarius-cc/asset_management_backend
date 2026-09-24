"""
WebSocket 路由配置
"""

from django.urls import re_path

from apps.notification.consumer import NotificationConsumer


websocket_urlpatterns = [
    # django-stubs 将 re_path 第二参标为 HttpResponse 工厂, channels as_asgi() 为 ASGI 可调用, 属桩不匹配
    re_path(r"ws/notifications/(?P<jobcode>\w+)/$", NotificationConsumer.as_asgi()),  # type: ignore[arg-type]
]
