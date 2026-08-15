"""
数据迁移脚本:将合同支付记录从文本格式迁移为JSON格式

文本格式示例:
"2024-01-15 10:00:00: 付款 10000 元 - 首付款\n2024-02-20 14:30:00: 付款 5000 元"

JSON格式示例:
{
  "payments": [
    {
      "id": "uuid",
      "date": "2024-01-15",
      "amount": 10000.00,
      "description": "首付款",
      "status": "approved",
      "created_at": "2024-01-15T10:00:00"
    }
  ],
  "total_paid": 15000.00,
  "last_payment_date": "2024-02-20"
}
"""

import json
import re
import uuid

from django.db import migrations


def parse_text_payment_record(text_record: str) -> dict:
    """
    解析文本格式的支付记录
    
    Args:
        text_record: 文本格式的支付记录
        
    Returns:
        解析后的JSON格式支付记录
    """
    default_record = {"payments": [], "total_paid": 0, "last_payment_date": None}
    
    if not text_record or not text_record.strip():
        return default_record
    
    # 解析文本格式
    # 格式: "2024-01-15 10:00:00: 付款 10000 元 - 首付款\n"
    pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}): 付款 ([\d.]+) 元(?: - (.+))?'
    matches = re.findall(pattern, text_record)
    
    payments = []
    total_paid = 0
    
    for date_str, amount_str, description in matches:
        try:
            amount = float(amount_str)
        except ValueError:
            continue
        
        payments.append({
            "id": str(uuid.uuid4()),
            "date": date_str.split(' ')[0],  # 只取日期部分
            "amount": amount,
            "description": description.strip() if description else "",
            "status": "approved",  # 历史记录默认为已审核
            "created_at": date_str,
            "payment_method": "bank_transfer",
            "operator": "system"
        })
        total_paid += amount
    
    return {
        "payments": payments,
        "total_paid": total_paid,
        "last_payment_date": payments[-1]["date"] if payments else None
    }


def migrate_paid_record_forward(apps, schema_editor):
    """正向迁移:将文本格式支付记录迁移为JSON格式"""
    Contract = apps.get_model('assetmanagement', 'Contract')
    
    migrated_count = 0
    skipped_count = 0
    error_count = 0
    
    for contract in Contract.objects.filter(paid_record__isnull=False).exclude(paid_record=''):
        old_record = contract.paid_record
        
        # 跳过已经是JSON格式的记录
        try:
            parsed = json.loads(old_record)
            if isinstance(parsed, dict) and 'payments' in parsed:
                skipped_count += 1
                continue
        except (json.JSONDecodeError, TypeError):
            pass
        
        # 解析文本格式
        try:
            new_record = parse_text_payment_record(old_record)
            contract.paid_record = json.dumps(new_record, ensure_ascii=False, default=str)
            
            # 同步更新amount_paid
            contract.amount_paid = new_record["total_paid"]
            
            # 更新has_payment标志
            contract.has_payment = len(new_record["payments"]) > 0
            
            contract.save(update_fields=['paid_record', 'amount_paid', 'has_payment', 'updated_at'])
            migrated_count += 1
        except Exception as e:
            print(f"迁移合同{contract.contract_code}失败: {e}")
            error_count += 1
    
    print(f"迁移完成: 成功{migrated_count}条, 跳过{skipped_count}条, 失败{error_count}条")


def migrate_paid_record_backward(apps, schema_editor):
    """反向迁移:将JSON格式支付记录迁移回文本格式"""
    Contract = apps.get_model('assetmanagement', 'Contract')
    
    for contract in Contract.objects.filter(paid_record__isnull=False).exclude(paid_record=''):
        try:
            record = json.loads(contract.paid_record)
            if not isinstance(record, dict) or 'payments' not in record:
                continue
        except (json.JSONDecodeError, TypeError):
            continue
        
        lines = []
        for payment in record.get('payments', []):
            if payment.get('status') == 'deleted':
                continue
            line = f"{payment['created_at']}: 付款 {payment['amount']} 元"
            if payment.get('description'):
                line += f" - {payment['description']}"
            lines.append(line)
        
        contract.paid_record = '\n'.join(lines) + '\n' if lines else ''
        contract.save(update_fields=['paid_record', 'updated_at'])


class Migration(migrations.Migration):
    """
    数据迁移:将合同支付记录从文本格式迁移为JSON格式
    
    注意:此迁移是数据迁移,不涉及表结构变更
    """
    
    dependencies = [
        ('assetmanagement', '0009_asset_warranty_manually_modified_and_more'),
    ]

    operations = [
        migrations.RunPython(
            migrate_paid_record_forward,
            migrate_paid_record_backward,
            hints={'model_name': 'contract'}
        ),
    ]
