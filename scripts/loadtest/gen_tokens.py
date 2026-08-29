"""
M-4 压测 token 预生成脚本（预发环境专用）

背景：login 5/min 限流阻挡 vuser 规模登录
方案：Django shell 一次性签发 N 个 access token 写入 tokens.json
      locust User.start() 从池取 token 注入 Authorization
安全：仅在预发 DB 使用 loadtest_user_* 用户，泄露面为零
"""

import json
import os
import sys
from pathlib import Path

import django


def setup_django():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
    os.environ["DJANGO_SUPERUSER_USERNAME"] = "loadtest_admin"
    os.environ["DJANGO_SUPERUSER_PASSWORD"] = "loadtest_pass_x123456"
    os.environ.setdefault("ALLOWED_HOSTS", "*")
    os.environ.setdefault("DB_NAME", "asset_management_pre")
    os.environ.setdefault("DB_USER", "postgres")
    os.environ.setdefault("DB_PASSWORD", "loadtest_db_pass")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("SECRET_KEY", "loadtest_secret_x1234567890abcdefghij")
    django.setup()


def main():
    setup_django()

    from django.contrib.auth import get_user_model
    from rest_framework_simplejwt.tokens import RefreshToken

    User = get_user_model()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50

    tokens = []
    for i in range(1, n + 1):
        username = f"loadtest_user_{i:03d}"
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={"is_active": True},
        )
        user.set_password("loadtest_pass_x123456")
        user.is_active = True
        user.save()
        refresh = RefreshToken.for_user(user)
        tokens.append({
            "username": username,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        })

    out_path = Path(__file__).resolve().parent / "tokens.json"
    out_path.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
    print(f"已生成 {len(tokens)} 个 token，写入 {out_path}")


if __name__ == "__main__":
    main()
