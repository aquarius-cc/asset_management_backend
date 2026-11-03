"""OP-05 员工审计快照脱敏回归测试(OC-3)

更新员工产生的 AuditLog before_data/after_data 不得含明文手机号(BF-165 的 WAI 判词
仅限 API 响应体, 落库快照消费方仅 IsAuditorOrAdmin, OC-3 红线适用)。
"""

import json

import pytest
from django.db import transaction
from django.test import TestCase

from core.audit_service import GenericAuditService
from core.models_audit import AuditLog


PHONE = "13812345678"
MASKED = "138****5678"


def _write_employee_update_audit(before_phone: str | None, after_phone: str | None) -> AuditLog:
    """模拟员工更新审计写入(GenericAuditService 唯一生产写入路径, on_commit 后落库)"""
    with TestCase.captureOnCommitCallbacks(execute=True):
        with transaction.atomic():
            GenericAuditService.log_operation(
                record_code="EMP-MASK-TEST",
                app_label="employee",
                operation_type="update",
                description="更新员工(OP-05 脱敏回归)",
                before_data={"employee_phone": before_phone} if before_phone is not None else {},
                after_data={"employee_phone": after_phone} if after_phone is not None else {},
            )
    return AuditLog.objects.filter(app_label="employee", operation_type="update").latest("id")


@pytest.mark.django_db
class TestEmployeeAuditMasking:
    def test_phone_update_snapshot_masked(self):
        log = _write_employee_update_audit(PHONE, PHONE)

        dumped = json.dumps([log.before_data, log.after_data], ensure_ascii=False)
        assert PHONE not in dumped
        assert log.before_data["employee_phone"] == MASKED
        assert log.after_data["employee_phone"] == MASKED

    def test_unchanged_phone_still_masked(self):
        """手机号未变更的普通更新同样脱敏(防「仅变更时脱敏」的假绿实现)"""
        log = _write_employee_update_audit(PHONE, PHONE)

        assert log.after_data["employee_phone"] == MASKED
