import subprocess
import json

result = subprocess.run(
    ['python', '-m', 'ruff', 'check', 'apps/', '--select', 'E402,E501', '--output-format', 'json'],
    capture_output=True,
    text=True
)

data = json.loads(result.stdout)
print(f"代码风格问题总数: {len(data)}\n")

# 按文件分组
from collections import defaultdict
file_issues = defaultdict(list)
for d in data:
    file_issues[d['filename']].append({
        'line': d['location']['row'],
        'code': d['code'],
        'message': d['message']
    })

print("=== 按文件分组 ===\n")
for filename, issues in sorted(file_issues.items()):
    print(f"{filename}:")
    for issue in issues[:3]:  # 只显示前3个
        print(f"  Line {issue['line']}: {issue['code']} - {issue['message'][:50]}...")
    if len(issues) > 3:
        print(f"  ... 还有 {len(issues) - 3} 个问题")
    print()
