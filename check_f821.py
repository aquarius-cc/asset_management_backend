import subprocess
import json

result = subprocess.run(
    ['python', '-m', 'ruff', 'check', 'apps/', '--select', 'F821', '--output-format', 'json'],
    capture_output=True,
    text=True
)

data = json.loads(result.stdout)
print(f"F821 errors: {len(data)}")

for d in data:
    print(f"{d['filename']}:{d['location']['row']}: {d['message']}")
