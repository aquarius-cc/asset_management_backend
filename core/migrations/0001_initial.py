"""
通用审计日志模型迁移
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('record_code', models.CharField(db_index=True, help_text='被操作记录的唯一编码', max_length=64, verbose_name='记录编码')),
                ('app_label', models.CharField(db_index=True, help_text='操作所属的应用', max_length=50, verbose_name='应用标识')),
                ('operation_type', models.CharField(choices=[('create', '创建'), ('update', '更新'), ('delete', '删除'), ('approve', '审批'), ('login', '登录'), ('logout', '登出'), ('permission_change', '权限变更'), ('state_change', '状态变更')], db_index=True, max_length=20, verbose_name='操作类型')),
                ('logging_id', models.CharField(blank=True, db_index=True, help_text='系统自动生成的日志记录唯一标识', max_length=50, unique=True, verbose_name='日志记录ID')),
                ('operation_time', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='操作时间')),
                ('operator_jobcode', models.CharField(blank=True, max_length=20, null=True, verbose_name='操作人工号')),
                ('operator_name', models.CharField(blank=True, max_length=100, null=True, verbose_name='操作人姓名')),
                ('before_data', models.JSONField(blank=True, null=True, verbose_name='变更前数据')),
                ('after_data', models.JSONField(blank=True, null=True, verbose_name='变更后数据')),
                ('description', models.TextField(verbose_name='操作描述')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, verbose_name='操作IP地址')),
            ],
            options={
                'verbose_name': '通用审计日志',
                'verbose_name_plural': '通用审计日志',
                'db_table': 'core_audit_log',
                'ordering': ['-operation_time'],
            },
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['record_code', '-operation_time'], name='core_audit__record__idx'),
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['app_label', 'operation_type'], name='core_audit__app_labe_idx'),
        ),
    ]
