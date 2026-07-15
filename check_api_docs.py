import os
import re

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

print("=== API文档检查 ===\n")

# 检查是否有drf-spectacular配置
print("1. 检查drf-spectacular配置:")
spectacular_installed = False
for root, dirs, files in os.walk('config'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            if 'drf_spectacular' in content or 'SPECTACULAR' in content:
                spectacular_installed = True
                print(f"  找到配置文件: {filepath}")
                break

if spectacular_installed:
    print("  ✅ drf-spectacular已配置")
else:
    print("  ❌ drf-spectacular未配置")

# 检查API端点
print("\n2. 检查API端点:")
api_endpoints = []
for root, dirs, files in os.walk('apps'):
    for file in files:
        if file == 'urls.py':
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            # 统计API端点数量
            endpoints = re.findall(r'path\([\'\"](.*?)[\'\"]', content)
            api_endpoints.extend([(filepath, ep) for ep in endpoints])

print(f"  找到 {len(api_endpoints)} 个API端点")

# 检查是否有@extend_schema装饰器
print("\n3. 检查@extend_schema装饰器:")
extend_schema_count = 0
for root, dirs, files in os.walk('apps'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            count = content.count('@extend_schema')
            extend_schema_count += count

print(f"  找到 {extend_schema_count} 处@extend_schema装饰器")

# 检查API端点是否有文档
print("\n4. 检查API端点文档覆盖率:")
if extend_schema_count > 0:
    print(f"  ✅ 有 {extend_schema_count} 个API端点有文档")
else:
    print("  ❌ 没有找到@extend_schema装饰器")
