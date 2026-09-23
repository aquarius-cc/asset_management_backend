"""
项目常量

本文件仅存分页/批量尺寸常量（DEFAULT_PAGE_SIZE / MAX_PAGE_SIZE / MAX_BATCH_SIZE，单一来源）。
一切枚举常量（状态/类型等选项集）必须定义在对应 Model 侧 TextChoices，禁止回流本文件。
"""

# ============================
# 分页配置
# ============================
DEFAULT_PAGE_SIZE: int = 20
MAX_PAGE_SIZE: int = 100


# ============================
# 批量操作常量
# ============================
# 【DR-1 收敛】单一事实来源: 全项目批量操作条目上限(序列化器/Service/View 统一引用)
MAX_BATCH_SIZE: int = 100
