import os
import re

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

print("=== Models文件审查 ===\n")

# 收集所有models文件
model_files = []
for root, dirs, files in os.walk('apps'):
    for file in files:
        if file == 'models.py' or (file.endswith('.py') and 'models' in root):
            model_files.append(os.path.join(root, file))

print(f"找到 {len(model_files)} 个models文件\n")

# 检查每个models文件
for filepath in model_files:
    print(f"\n--- {filepath} ---")
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 统计模型类数量
    model_classes = re.findall(r'class \w+\(.*Model.*\):', content)
    print(f"  模型类数量: {len(model_classes)}")
    
    # 检查是否有RECORDCODE_PREFIX
    if 'RECORDCODE_PREFIX' in content:
        prefixes = re.findall(r'RECORDCODE_PREFIX\s*=\s*["\'](\w+)["\']', content)
        print(f"  RECORDCODE_PREFIX: {prefixes}")
    
    # 检查是否有BaseModel继承
    if 'BaseModel' in content:
        print(f"  继承自BaseModel: 是")
    
    # 检查是否有软删除
    if 'is_deleted' in content:
        print(f"  支持软删除: 是")
    
    # 检查文件行数
    lines = content.count('\n') + 1
    print(f"  文件行数: {lines}")
