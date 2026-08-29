"""
管理命令：check_admin — 验证超管存在性（M-2 发布门禁）

用法：python manage.py check_admin
返回：
  - 超管存在：exit 0，打印用户名
  - 超管不存在：exit 2，打印指引（非阻断启动，仅用于发布检查单）
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = "检查是否存在超级管理员（M-2 发布验证门禁）"

    def handle(self, *args, **options):
        admins = User.objects.filter(is_superuser=True, is_active=True)
        if admins.exists():
            admin = admins.first()
            self.stdout.write(self.style.SUCCESS(
                f"[PASS] 超管存在：username={admin.username} (id={admin.id})"
            ))
            return 0
        else:
            self.stderr.write(self.style.ERROR(
                "[FAIL] 未发现超级管理员！\n"
                "  指引：执行 python manage.py createsuperuser --noinput ，"
                "或在生产容器设置 DJANGO_SUPERUSER_USERNAME / PASSWORD 后重启。"
            ))
            return 2
