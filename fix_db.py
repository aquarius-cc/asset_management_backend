import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

import django
django.setup()

from django.db import connection
cursor = connection.cursor()

# 删除多余的storage_manager列（保留storage_manager_id外键列）
try:
    cursor.execute("ALTER TABLE `am_storage` DROP COLUMN `storage_manager`")
    print("Dropped storage_manager column")
except Exception as e:
    print(f"Error dropping storage_manager: {e}")

# 检查结果
cursor.execute("DESCRIBE am_storage")
columns = [row[0] for row in cursor.fetchall()]
print(f"\nColumns after fix: {columns}")
print(f"storage_manager_id in columns: {'storage_manager_id' in columns}")
print(f"storage_manager in columns: {'storage_manager' in columns}")
