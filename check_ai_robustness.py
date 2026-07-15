import os
import re

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

print("=== AI鲁棒性规范检查 (AR-1 ~ AR-5) ===\n")

# AR-1: 不确定的API参数必须标注TODO_AI_CONFIRM
print("AR-1: 不确定的API参数必须标注TODO_AI_CONFIRM")
print("  检查中...")
# 检查代码中是否有TODO_AI_CONFIRM标注
todo_count = 0
for root, dirs, files in os.walk('apps'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            todos = re.findall(r'#\s*TODO_AI_CONFIRM', content)
            todo_count += len(todos)
print(f"  找到 {todo_count} 处 TODO_AI_CONFIRM 标注\n")

# AR-2: 高风险代码必须标注AI_REVIEW_NEEDED
print("AR-2: 高风险代码必须标注AI_REVIEW_NEEDED")
print("  检查中...")
# 检查代码中是否有AI_REVIEW_NEEDED标注
review_count = 0
for root, dirs, files in os.walk('apps'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            reviews = re.findall(r'#\s*AI_REVIEW_NEEDED', content)
            review_count += len(reviews)
print(f"  找到 {review_count} 处 AI_REVIEW_NEEDED 标注\n")

# AR-3: 所有外部调用必须设置超时和重试
print("AR-3: 所有外部调用必须设置超时和重试")
print("  检查中...")
# 检查代码中是否有外部调用
print("  ⚠️ 需要检查代码中是否有外部调用（HTTP、RPC、DB操作）\n")

# AR-4: 超时时间及重试次数必须由配置文件管理
print("AR-4: 超时时间及重试次数必须由配置文件管理")
print("  检查中...")
# 检查是否有配置文件管理超时和重试
print("  ⚠️ 需要检查是否有配置文件管理超时和重试\n")

# AR-5: AI生成代码后应自动执行静态检查
print("AR-5: AI生成代码后应自动执行静态检查")
print("  检查中...")
# 检查是否有静态检查配置
print("  ⚠️ 需要检查是否有静态检查配置（ruff、mypy等）\n")

print("=== AI鲁棒性规范检查完成 ===")
print("\n总结:")
print(f"  - AR-1: 找到 {todo_count} 处 TODO_AI_CONFIRM 标注")
print(f"  - AR-2: 找到 {review_count} 处 AI_REVIEW_NEEDED 标注")
print("  - AR-3: 需要检查代码中是否有外部调用")
print("  - AR-4: 需要检查是否有配置文件管理超时和重试")
print("  - AR-5: 需要检查是否有静态检查配置")
