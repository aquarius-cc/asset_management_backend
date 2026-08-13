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
        migrations.AddField(
            model_name="employee",
            name="auth_user",
            field=models.OneToOneField(
                null=True,
                blank=True,
                on_delete=models.SET_NULL,
                related_name="employee",
                to="authusermanagement.authuser",
                verbose_name="绑定的认证账号",
                help_text="绑定的认证账号,null 表示未绑定",
            ),
        ),
        migrations.AddConstraint(
            model_name="employee",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_deleted=False),
                fields=["auth_user"],
                name="unique_employee_auth_user_not_deleted",
            ),
        ),
    ]
