"""
填充现有 RecycleAsset 记录的 recycle_record_code 并设为唯一非空（阶段2）

1. 为所有 recycle_record_code 为空的现有记录生成唯一编码
2. 将字段设为 unique=True, null=False, blank=False
3. 新增 recycle_record_code 索引
"""

import secrets
import string

from django.db import migrations, models
from django.utils import timezone


def _generate_recycle_record_code() -> str:
    """生成唯一回收记录编码: RECYCLE-YYYYMMDD-XXXXXXXX"""
    prefix = "RECYCLE"
    date_str = timezone.now().strftime("%Y%m%d")
    random_suffix = "".join(
        secrets.choice(string.ascii_uppercase + string.digits)
        for _ in range(8)
    )
    return f"{prefix}-{date_str}-{random_suffix}"


def fill_recycle_record_codes(apps, schema_editor):
    """
    为所有 recycle_record_code 为空的现有记录生成唯一编码。

    使用数据库级别的唯一约束检查避免冲突。
    """
    RecycleAsset = apps.get_model("assetmanagement", "RecycleAsset")
    for record in RecycleAsset.objects.filter(recycle_record_code__isnull=True):
        for _ in range(5):
            code = _generate_recycle_record_code()
            if not RecycleAsset.objects.filter(recycle_record_code=code).exists():
                record.recycle_record_code = code
                record.save(update_fields=["recycle_record_code"])
                break


class Migration(migrations.Migration):

    dependencies = [
        ("assetmanagement", "0008_add_recycle_record_code"),
    ]

    operations = [
        # Stripped: all ops are no-ops (0001_initial + consolidated is source of truth)
    ]
