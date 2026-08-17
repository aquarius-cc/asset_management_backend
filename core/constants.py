# d:\CodeDemo\Python\asset_management_backend\core\constants.py
"""
项目常量

提供项目中使用的所有常量定义:
- 资产相关状态常量
- 用户和部门状态常量
- 分页配置
"""

# ============================
# 资产状态常量
# 【P2-6 修复】与 Asset.AssetStatus TextChoices 保持一致(直接引用避免重复定义)
# 注意:避免循环导入,此处保留独立定义,与 model 的 AssetStatus.choices 值一致
ASSET_STATUS_CHOICES: list[tuple[str, str]] = [
    ("in_store", "在库"),
    ("in_use", "在用"),
    ("recycled_pending", "已回收待发放"),
    ("broken", "已损坏"),
    ("repairing", "维修中"),
    ("lost", "已遗失"),
    ("damaged", "待报废"),
    ("scrapped", "已报废"),
]

# 资产外观状态
ASSET_APPEARANCE_CHOICES: list[tuple[str, str]] = [
    ("newly", "新增加资产"),
    ("used", "已使用资产"),
    ("damaged", "待报废资产"),
    ("waste", "已报废资产"),
]

# 出库类型
OUTASSET_TYPE_CHOICES: list[tuple[str, str]] = [
    ("receive", "领用"),
    ("borrow", "借用"),
]

# ============================
# 员工状态常量(与 usermanagement/models.py 保持一致)
# ============================
EMPLOYEE_STATUS_CHOICES: list[tuple[str, str]] = [
    ("active", "在职员工"),
    ("left", "离职员工"),
    ("retirement", "退休员工"),
]

# ============================
# 部门状态常量
# ============================
DEPARTMENT_STATUS_CHOICES: list[tuple[str, str]] = [
    ("active", "正常"),
    ("inactive", "停用"),
]

# ============================
# 审批状态常量
# ============================
APPROVAL_STATUS_CHOICES: list[tuple[str, str]] = [
    ("pending", "待审批"),
    ("approved", "已批准"),
    ("rejected", "已拒绝"),
]

# ============================
# 合同类型常量
# ============================
CONTRACT_TYPE_CHOICES: list[tuple[str, str]] = [
    ("tender_procurement", "招标采购合同"),
    ("service", "服务合同"),
    ("information_construction", "信息化建设合同"),
    ("direct_procurement", "直接采购合同"),
]

CONTRACT_SETTLEMENT_CHOICES: list[tuple[str, str]] = [
    ("pending", "待结算"),
    ("settling_up", "结算中"),
    ("settled", "已结算"),
]

# ============================
# 仓库类型常量
# ============================
STORAGE_TYPE_CHOICES: list[tuple[str, str]] = [
    ("newasset", "新货仓库"),
    ("recycle", "回收仓库"),
    ("broken", "损坏存放出库"),
    ("damaged", "待报废仓库"),
]

# ============================
# 硬盘状态常量
# ============================
HARDDISK_STATUS_CHOICES: list[tuple[str, str]] = [
    ("active", "正常"),
    ("repair", "维修"),
    ("scrap", "报废"),
    ("lost", "丢失"),
    ("damaged", "损坏"),
]

# ============================
# 分页配置
# ============================
DEFAULT_PAGE_SIZE: int = 20
MAX_PAGE_SIZE: int = 100
