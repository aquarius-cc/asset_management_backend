import subprocess
import json

result = subprocess.run(
    ['python', '-m', 'ruff', 'check', 'apps/', '--select', 'E501', '--output-format', 'json'],
    capture_output=True,
    text=True
)

data = json.loads(result.stdout)
print(f"E501错误: {len(data)}\n")

for d in data:
    print(f"{d['filename']}:{d['location']['row']}: {d['message'][:80]}...")
