# d:\CodeDemo\Python\asset_management_backend\core\constants.py
"""
项目常量

提供项目中使用的所有常量定义：
- 资产相关状态常量
- 用户和部门状态常量
- 错误码定义
- 分页配置
"""

from typing import List, Tuple, Dict

# ============================
# 资产状态常量
# ============================
ASSET_STATUS_CHOICES: List[Tuple[str, str]] = [
    ('in_store', '在库资产'),
    ('in_use', '在用资产'),
    ('in_scrapped', '报废资产'),
]

# 资产外观状态
ASSET_APPEARANCE_CHOICES: List[Tuple[str, str]] = [
    ('newly', '新增加资产'),
    ('used', '已使用资产'),
    ('damaged', '待报废资产'),
    ('waste', '已报废资产'),
]

# 出库类型
OUTASSET_TYPE_CHOICES: List[Tuple[str, str]] = [
    ('receive', '领用'),
    ('borrow', '借用'),
]

# ============================
# 员工状态常量（与 usermanagement/models.py 保持一致）
# ============================
EMPLOYEE_STATUS_CHOICES: List[Tuple[str, str]] = [
    ('active', '在职员工'),
    ('left', '离职员工'),
    ('retirement', '退休员工'),
]

# ============================
# 部门状态常量
# ============================
DEPARTMENT_STATUS_CHOICES: List[Tuple[str, str]] = [
    ('active', '正常'),
    ('inactive', '停用'),
]

# ============================
# 审批状态常量
# ============================
APPROVAL_STATUS_CHOICES: List[Tuple[str, str]] = [
    ('pending', '待审批'),
    ('approved', '已批准'),
    ('rejected', '已拒绝'),
]

# ============================
# 合同类型常量
# ============================
CONTRACT_TYPE_CHOICES: List[Tuple[str, str]] = [
    ('purchase', '采购合同'),
    ('service', '服务合同'),
    ('information_construction', '信息化建设合同'),
    ('direct_procurement', '直接采购合同'),
]

CONTRACT_SETTLEMENT_CHOICES: List[Tuple[str, str]] = [
    ('pending', '待结算'),
    ('settled', '已结算'),
]

# ============================
# 仓库类型常量
# ============================
STORAGE_TYPE_CHOICES: List[Tuple[str, str]] = [
    ("newasset", "新货仓库"),
    ("recycle", "回收仓库"),
    ("damaged", "待报废仓库"),
]

# ============================
# 硬盘状态常量
# ============================
HARDDISK_STATUS_CHOICES: List[Tuple[str, str]] = [
    ("active", "正常"),
    ("repair", "维修"),
    ("scrap", "报废"),
    ("lost", "丢失"),
    ("damaged", "损坏"),
]

# ============================
# 错误码常量
# ============================
ERROR_CODES: Dict[str, str] = {
    'VALIDATION_ERROR': 'E001',
    'NOT_FOUND': 'E002',
    'PERMISSION_DENIED': 'E003',
    'BUSINESS_LOGIC_ERROR': 'E004',
    'RESOURCE_CONFLICT': 'E005',
    'INTERNAL_ERROR': 'E006',
}

# ============================
# 分页配置
# ============================
DEFAULT_PAGE_SIZE: int = 20
MAX_PAGE_SIZE: int = 100