"""
添加 recycle_record_code 字段（阶段1：允许为空）

为 RecycleAsset 模型新增 recycle_record_code 字段，
先允许为空，后续通过数据迁移填充现有记录。
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assetmanagement", "0007_alter_asset_asset_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="recycleasset",
            name="recycle_record_code",
            field=models.CharField(
                max_length=30,
                verbose_name="回收记录编码",
                help_text="唯一回收记录编码，格式: RECYCLE-YYYYMMDD-XXXXXXXX",
                null=True,
                blank=True,
            ),
        ),
    ]
