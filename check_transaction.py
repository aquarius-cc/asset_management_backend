import os
import re

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

# 检查所有Service文件中的@transaction.atomic装饰器
service_files = []
for root, dirs, files in os.walk('apps'):
    for file in files:
        if file.endswith('_service.py') or file == 'services.py':
            service_files.append(os.path.join(root, file))

print("=== Service文件列表 ===")
for f in service_files:
    print(f"  {f}")

print("\n=== @transaction.atomic 装饰器统计 ===")
total_methods = 0
decorated_methods = 0

for filepath in service_files:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # 统计方法数
    methods = re.findall(r'def \w+\(', content)
    total_methods += len(methods)
    
    # 统计有@transaction.atomic装饰器的方法数
    decorated = re.findall(r'@transaction\.atomic\s+def \w+\(', content)
    decorated_methods += len(decorated)
    
    if decorated:
        print(f"  {filepath}: {len(decorated)} 个方法有装饰器")

print(f"\n总计: {total_methods} 个方法, {decorated_methods} 个有@transaction.atomic装饰器")
print(f"覆盖率: {decorated_methods/total_methods*100:.1f}%")
