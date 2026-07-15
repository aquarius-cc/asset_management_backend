import subprocess
import json

result = subprocess.run(
    ['python', '-m', 'ruff', 'check', 'apps/', '--select', 'F821', '--output-format', 'json'],
    capture_output=True,
    text=True
)

data = json.loads(result.stdout)
print(f"Critical errors (F821 - undefined names): {len(data)}")

for d in data:
    print(f"\n{d['filename']}:{d['location']['row']}:")
    print(f"  Code: {d['code']}")
    print(f"  Message: {d['message']}")
    if 'fix' in d and d['fix']:
        print(f"  Fix: {d['fix']['message']}")
