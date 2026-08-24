# 为 logging_id 添加唯一约束
#
# 注意：此迁移需要在历史数据的 logging_id 填充完毕后再执行。
# 如果数据库中已有空字符串的 logging_id 记录，需要先处理这些记录。

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assetmanagement', '0003_assetoperationlog_logging_id_and_more'),
    ]

    operations = [
        # Stripped: all ops are no-ops (0001_initial + consolidated is source of truth)
    ]
