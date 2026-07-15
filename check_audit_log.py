import os
import re

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

# 检查所有Service文件中的AuditLogger调用
service_files = []
for root, dirs, files in os.walk('apps'):
    for file in files:
        if file.endswith('_service.py') or file == 'services.py':
            service_files.append(os.path.join(root, file))

print("=== AuditLogger 调用统计 ===")
total_calls = 0

for filepath in service_files:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 统计AuditLogger调用
    calls = re.findall(r'AuditLogger\.\w+', content)
    if calls:
        print(f"  {filepath}: {len(calls)} 处调用")
        total_calls += len(calls)

print(f"\n总计: {total_calls} 处 AuditLogger 调用")

# 检查状态变更是否都有审计日志
print("\n=== 状态变更方法检查 ===")
state_change_methods = ['outasset', 'recycle', 'mark_broken', 'mark_lost', 'damaged', 'approve', 'reject', 'repair_done', 'repair_failed', 'found_and_return']

for filepath in service_files:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    for method in state_change_methods:
        if f'def {method}' in content or f'{method}(' in content:
            # 检查该方法是否有AuditLogger调用
            method_pattern = rf'def {method}\([^)]*\):.*?(?=\ndef |\nclass |\Z)'
            method_match = re.search(method_pattern, content, re.DOTALL)
            if method_match:
                method_body = method_match.group()
                if 'AuditLogger' in method_body:
                    print(f"  {filepath}:{method} - ✅ 有审计日志")
                else:
                    print(f"  {filepath}:{method} - ⚠️ 无审计日志")
