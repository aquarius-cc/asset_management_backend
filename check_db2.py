import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

import django
django.setup()

from django.db import connection
cursor = connection.cursor()

# 检查migration记录
cursor.execute("SELECT app, name FROM django_migrations WHERE app='assetmanagement'")
migrations = cursor.fetchall()
print("=== assetmanagement migrations ===")
for app, name in migrations:
    print(f"  {name}")

# 检查storage表结构
cursor.execute("SHOW CREATE TABLE am_storage")
result = cursor.fetchone()
print(f"\n=== am_storage CREATE TABLE ===")
print(f"  {result[1]}")
