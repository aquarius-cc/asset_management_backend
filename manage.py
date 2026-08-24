#!/usr/bin/env python
"""
Django 管理命令行工具

资产管理系统的 Django 管理脚本,用于:
- 数据库迁移 (migrate)
- 创建超级管理员 (createsuperuser)
- 运行开发服务器 (runserver)
- 运行测试 (test)
- 生成 API 文档 (spectacular)

详细用法请参考:https://docs.djangoproject.com/zh-hans/6.0/ref/django-admin/

【注意事项】
- 默认使用 development 配置
- 生产环境请设置 DJANGO_SETTINGS_MODULE=config.settings.production
"""

import os
import sys


def main() -> None:
    """
    执行 Django 管理命令

    设置 Django 设置模块并执行命令行工具。
    """
    # 【易错点】默认使用 development 配置
    # 生产环境应使用:config.settings.production
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "无法导入 Django。请确认是否已安装 Django:\n"
            "  pip install Django\n"
            "或者是否在虚拟环境中:\n"
            "  source venv/bin/activate  # Linux/macOS\n"
            "  venv\\Scripts\\activate     # Windows"
        ) from exc

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
