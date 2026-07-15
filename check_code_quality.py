import subprocess
import json

result = subprocess.run(
    ['python', '-m', 'ruff', 'check', 'apps/', '--select', 'E,F', '--output-format', 'json'],
    capture_output=True,
    text=True
)

data = json.loads(result.stdout)
print(f"Total errors: {len(data)}")

# 按文件分组
from collections import Counter
file_counts = Counter(d['filename'] for d in data)
print("\nErrors by file:")
for filename, count in file_counts.most_common(10):
    print(f"  {filename}: {count}")

# 按错误类型分组
code_counts = Counter(d['code'] for d in data)
print("\nErrors by type:")
for code, count in code_counts.most_common(10):
    print(f"  {code}: {count}")
