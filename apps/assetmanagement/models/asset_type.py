"""
资产类型管理模型
"""

from typing import TYPE_CHECKING

from django.db import models

from core.models import BaseModel


if TYPE_CHECKING:
    from django.db.models import Manager

# 资产类型层级最大限制(level 0-5,共 6 层)
MAX_ASSET_TYPE_LEVEL = 5


class AssetType(BaseModel):
    """
    资产类型管理模型

    用于定义资产的分类,支持树形层级结构,最大层级限制为 6 层。

    树形关联设计(方案 D):
    - parent: FK 指向父级 recordcode,保证引用稳定性
    - path: 物化路径,如 /ASSETTYPE-001/IT-001/DEV-001,加速子孙查询
    - parent_code: 旧字段,迁移完成后删除

    继承 BaseModel 获得:recordcode、is_active、is_deleted、
    created_at、updated_at、SoftDeleteManager、delete/restore/hard_delete。
    """

    if TYPE_CHECKING:
        objects: "Manager"

    RECORDCODE_PREFIX = "ASSETTYPE"

    type_code = models.CharField(
        max_length=30, default="", verbose_name="类型编码", help_text="资产类型唯一编码(用于树形结构标识)"
    )
    type_name = models.CharField(max_length=100, default="", verbose_name="类型名称", help_text="资产类型的显示名称")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
        to_field="recordcode",
        verbose_name="父级类型",
        help_text="父级资产类型(FK 指向 recordcode),null 表示顶级",
    )
    path = models.CharField(
        max_length=500,
        default="",
        blank=True,
        verbose_name="物化路径",
        help_text="从根到当前节点的完整路径,如 /ASSETTYPE-001/IT-001/DEV-001",
    )
    parent_code = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        verbose_name="父级编码(旧)",
        help_text="【已废弃】迁移完成后将删除,新代码请使用 parent FK",
    )
    level = models.IntegerField(default=0, verbose_name="层级", help_text="资产类型在树形结构中的层级,顶级为0")
    type_description = models.TextField(null=True, blank=True, verbose_name="类型描述", help_text="资产类型的详细描述")
    sort_order = models.IntegerField(
        default=0, verbose_name="排序", help_text="同级资产类型之间的排序权重,数字越小越靠前"
    )

    class Meta:
        verbose_name = "资产分类管理"
        verbose_name_plural = "资产分类管理"
        db_table = "am_asset_type"
        constraints = [
            models.UniqueConstraint(
                fields=["type_code"],
                condition=models.Q(is_deleted=False),
                name="unique_type_code_not_deleted",
            ),
            models.UniqueConstraint(
                fields=["type_name"],
                condition=models.Q(is_deleted=False),
                name="unique_type_name_not_deleted",
            ),
        ]
        indexes = [
            models.Index(fields=["parent"], name="idx_asset_type_parent_fk"),
            models.Index(fields=["path"], name="idx_asset_type_path"),
            models.Index(fields=["level"]),
            models.Index(fields=["parent_code"], name="idx_asset_type_parent_old"),
        ]

    def __str__(self) -> str:
        return f"{self.type_name}({self.type_code})"
