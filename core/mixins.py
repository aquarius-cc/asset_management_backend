"""
自定义 Mixins

提供通用的视图扩展功能:
- LoggingMixin: 自动记录操作日志
- GetSerializerClassMixin: 根据动作返回不同的序列化器
- ResponseWrapperMixin: 统一响应格式
- PaginateAndRespondMixin: 分页并返回统一响应
"""

import logging
from typing import Any

from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.serializers import Serializer

from utils.response_utils import error_response, success_response


# 配置日志记录器
logger = logging.getLogger(__name__)


class LoggingMixin:
    """
    自动记录操作的 Mixin

    在执行创建、更新、删除操作时自动记录日志信息,便于调试和追踪。
    使用 logging 模块而不是 print,便于生产环境日志管理。
    """

    def perform_create(self, serializer: Serializer[Any]) -> None:
        """创建操作前记录日志"""
        action = f"创建 {serializer.Meta.model.__name__ if hasattr(serializer, 'Meta') and hasattr(serializer.Meta, 'model') else '资源'}"
        logger.info(f"[操作日志] {action} - 用户: {self.request.user}")  # type: ignore[attr-defined]
        super().perform_create(serializer)  # type: ignore[misc]

    def perform_update(self, serializer: Serializer[Any]) -> None:
        """更新操作前记录日志"""
        action = f"更新 {serializer.Meta.model.__name__ if hasattr(serializer, 'Meta') and hasattr(serializer.Meta, 'model') else '资源'}"
        logger.info(f"[操作日志] {action} - 用户: {self.request.user}")  # type: ignore[attr-defined]
        super().perform_update(serializer)  # type: ignore[misc]

    def perform_destroy(self, instance: Any) -> None:
        """删除操作前记录日志"""
        action = f"删除 {instance.__class__.__name__}"
        logger.info(f"[操作日志] {action} - 用户: {self.request.user}")  # type: ignore[attr-defined]
        super().perform_destroy(instance)  # type: ignore[misc]


class GetSerializerClassMixin:
    """
    根据动作返回不同的序列化器

    通过 `serializer_action_classes` 属性配置不同动作对应的序列化器,
    实现同一个视图集在不同操作中使用不同的序列化器。
    Example:
        class MyViewSet(GetSerializerClassMixin, viewsets.ModelViewSet):
            serializer_class = DefaultSerializer
            serializer_action_classes = {
                'create': CreateSerializer,
                'update': UpdateSerializer,
            }
    """

    serializer_class: type[Serializer[Any]] | None = None
    serializer_action_classes: dict[str, type[Serializer[Any]]] = {}

    def get_serializer_class(self) -> type[Serializer[Any]]:
        """根据当前动作返回对应的序列化器"""
        if self.action in self.serializer_action_classes:  # type: ignore[attr-defined]
            return self.serializer_action_classes[self.action]  # type: ignore[attr-defined]
        return super().get_serializer_class()  # type: ignore[no-any-return, misc]  # type: ignore[no-any-return]


class ResponseWrapperMixin:
    """
    统一响应格式

    将视图响应统一为标准格式:{"code": 状态码, "msg": "消息", "data": {}}
    使用 utils.response_utils 中的工具函数确保响应格式一致性。
    注意:
    - 仅捕获非 DRF 异常,让 DRF 的 APIException 子类正常传播到 exception handler
    - create/update/destroy 方法返回统一的 {code, msg, data} 格式
    - 捕获异常时不在响应中暴露内部错误详情
    """

    def list(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """
        列表查询响应(统一格式)

        流程:
        1. 过滤查询集
        2. 如果有分页参数 → 调用分页器的 get_paginated_response(已包装 success_response)
        3. 如果无分页参数 → 手动包装 success_response
        """
        try:
            queryset = self.filter_queryset(self.get_queryset())  # type: ignore[attr-defined]

            # 尝试分页
            page = self.paginate_queryset(queryset)  # type: ignore[attr-defined]
            if page is not None:
                serializer = self.get_serializer(page, many=True)  # type: ignore[attr-defined]
                return self.get_paginated_response(serializer.data)  # type: ignore[attr-defined, no-any-return]

            # 无分页参数时,手动包装
            serializer = self.get_serializer(queryset, many=True)  # type: ignore[attr-defined]
            return success_response(data={"count": queryset.count(), "results": serializer.data}, message="查询成功")
        except APIException:
            # 【修复 S9】让 DRF APIException 正常传播,不吞掉
            raise
        except Http404:
            logger.warning("资源不存在")
            return error_response(message="资源不存在或已被删除", status_code=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            # 【修复 S9】生产环境不返回详细错误,仅记录日志
            logger.error(f"列表查询失败: {e!s}", exc_info=True)
            return error_response(message="查询失败,请稍后重试", status_code=500)

    def create(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """
        创建资源响应(统一格式)

        流程:
        1. 验证请求数据
        2. 调用 perform_create 方法创建资源
        3. 返回成功响应
        """
        try:
            serializer = self.get_serializer(data=request.data)  # type: ignore[attr-defined]
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)  # type: ignore[attr-defined]

            return success_response(data=serializer.data, message="创建成功", status_code=status.HTTP_201_CREATED)
        except APIException:
            # 【修复 S9】让 DRF APIException 正常传播
            raise
        except Exception as e:
            logger.error(f"创建资源失败: {e!s}", exc_info=True)
            return error_response(message="创建失败,请稍后重试", status_code=500)

    def retrieve(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """
        获取单个资源响应(统一格式)

        流程:
        1. 获取资源实例
        2. 序列化资源实例
        3. 返回成功响应
        """
        try:
            instance = self.get_object()  # type: ignore[attr-defined]
            serializer = self.get_serializer(instance)  # type: ignore[attr-defined]
            return success_response(data=serializer.data, message="查询成功")
        except Http404:
            logger.warning("资源不存在")
            return error_response(message="资源不存在或已被删除", status_code=status.HTTP_404_NOT_FOUND)
        except APIException:
            # 【修复 S9】让 DRF APIException 正常传播
            raise
        except Exception as e:
            logger.error(f"获取详情失败: {e!s}", exc_info=True)
            return error_response(message="查询失败,请稍后重试", status_code=500)

    def update(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """
        更新资源响应(统一格式)
        支持全量更新(PUT)和部分更新(PATCH)
        流程:
        1. 获取资源实例
        2. 验证请求数据
        3. 调用 perform_update 方法更新资源
        4. 返回成功响应
        """
        try:
            partial = kwargs.pop("partial", False)
            instance = self.get_object()  # type: ignore[attr-defined]
            serializer = self.get_serializer(instance, data=request.data, partial=partial)  # type: ignore[attr-defined]
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)  # type: ignore[attr-defined]

            return success_response(data=serializer.data, message="更新成功")
        except APIException:
            # 【修复 S9】让 DRF APIException 正常传播
            raise
        except Exception as e:
            logger.error(f"更新资源失败: {e!s}", exc_info=True)
            return error_response(message="更新失败,请稍后重试", status_code=500)

    def destroy(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """
        删除资源响应(统一格式)

        流程:
        1. 获取资源实例
        2. 调用 perform_destroy 方法删除资源
        3. 返回成功响应
        """
        try:
            instance = self.get_object()  # type: ignore[attr-defined]
            self.perform_destroy(instance)  # type: ignore[attr-defined]

            return success_response(data={}, message="删除成功", status_code=status.HTTP_200_OK)
        except Http404:
            logger.warning("删除失败,资源不存在")
            return error_response(message="资源不存在或已被删除", status_code=status.HTTP_404_NOT_FOUND)
        except APIException:
            # 【修复 S9】让 DRF APIException 正常传播
            raise
        except Exception as e:
            logger.error(f"删除资源失败: {e!s}", exc_info=True)
            return error_response(message="删除失败,请稍后重试", status_code=500)


class PaginateAndRespondMixin:
    """
    分页并返回统一响应 Mixin

    提供通用的分页查询响应方法,支持有分页参数时分页,无参数时返回全部数据。

    使用方式:
        class MyViewSet(PaginateAndRespondMixin, ModelViewSet):
            def some_action(self, request):
                records = MyModel.objects.filter(...)
                return self._paginate_and_respond(records)
    """

    def _paginate_and_respond(self, queryset: Any) -> Response:
        """
        分页并返回统一响应

        Args:
            queryset: 查询集

        Returns:
            Response: 分页响应或全部数据响应
        """
        page = self.paginate_queryset(queryset)  # type: ignore[attr-defined]
        if page is not None:
            serializer = self.get_serializer(page, many=True)  # type: ignore[attr-defined]
            return self.get_paginated_response(serializer.data)  # type: ignore[attr-defined, no-any-return]
        serializer = self.get_serializer(queryset, many=True)  # type: ignore[attr-defined]
        return success_response(data=serializer.data)
