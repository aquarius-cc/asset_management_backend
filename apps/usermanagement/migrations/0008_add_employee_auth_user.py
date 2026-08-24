"""
Employee ↔ AuthUser 绑定功能:添加 auth_user 字段

新增 Employee.auth_user OneToOneField(nullable),
建立员工与认证账号的 1:1 可选绑定关系。
添加条件唯一约束,确保非删除员工的 auth_user 唯一性。
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("usermanagement", "0005_rbac_permission_tables"),
        ("authusermanagement", "0001_initial"),
    ]

    operations = [
        # Stripped: all ops are no-ops (0001_initial + consolidated is source of truth)
    ]
