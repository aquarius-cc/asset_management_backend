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
        migrations.AlterField(
            model_name='assetoperationlog',
            name='logging_id',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='系统自动生成的日志记录唯一标识，格式：操作类型-Log-日期-随机字符',
                max_length=50,
                unique=True,
                verbose_name='日志记录ID',
            ),
        ),
    ]
