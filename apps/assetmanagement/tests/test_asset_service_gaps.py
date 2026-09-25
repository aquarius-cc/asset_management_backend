"""AssetService 变异杀伤补测(B-M2, T5 精确断言)

针对 asset_service.py 幸存变异体的精确断言补强:
- AssetCodeGenerator: 编码格式/层级路径截断/重试上限/默认批数
- ASSET_UPDATE_IMMUTABLE_FIELDS: 逐字段禁改
- create_asset: qr_code JSON 键值/默认批数/预设 qr 保留
- 错误文案逐字: update/delete/change/员工解析
- 审计快照: change_status/change_outasset_employee 的 before/after 与状态日志
- generate_qr_code_image: 扫码 URL 与构造参数
- 原子性回滚: 中途审计失败不落库(CT-1)
"""

import json
import string
from unittest import mock

import pytest

from apps.assetmanagement.models import Asset, AssetOperationLog, AssetType, DamagedAsset, OutAsset
from apps.assetmanagement.services.asset_service import AssetCodeGenerator, AssetService
from core.exceptions import AppValidationError, NotFoundError


@pytest.mark.django_db
class TestAssetCodeGeneratorKills:
    """编码生成器精确断言"""

    def test_single_code_format_exact(self, asset_type):
        """单编码: 后缀 8 位大写字母+数字, 无序号尾巴"""
        code = AssetCodeGenerator.generate(asset_type)[0]
        assert code.startswith("AT001-")
        suffix = code.split("-")[-1]
        assert len(suffix) == 8
        assert all(c in string.ascii_uppercase + string.digits for c in suffix)
        assert not suffix.isdigit() or len(suffix) == 8

    def test_single_code_has_no_sequence_suffix(self, asset_type):
        """批数 1: 编码不含 0001 序号尾巴(固定 uuid 消除随机)"""
        with mock.patch.object(AssetCodeGenerator, "_generate_uuid_hex", return_value="ABCD1234"):
            code = AssetCodeGenerator.generate(asset_type, 1)[0]
        assert code == "AT001-ABCD1234"
        assert not code.endswith("0001")

    def test_multi_code_sequence_exact(self, asset_type):
        """批数 2: 两条编码带 0001/0002 序号且互不相同"""
        codes = AssetCodeGenerator.generate(asset_type, 2)
        assert len(codes) == 2
        assert codes[0].endswith("0001")
        assert codes[1].endswith("0002")
        assert len(set(codes)) == 2

    def test_generate_default_purchase_number_is_one(self, asset_type):
        """generate 默认批数为 1"""
        assert len(AssetCodeGenerator.generate(asset_type)) == 1

    def test_unique_check_default_purchase_number_is_one(self, asset_type):
        """generate_with_unique_check 默认批数为 1"""
        assert len(AssetCodeGenerator.generate_with_unique_check(asset_type)) == 1

    def test_generate_rejects_zero_with_exact_message(self, asset_type):
        """批数 < 1 拒绝且文案逐字"""
        with pytest.raises(ValueError) as exc:
            AssetCodeGenerator.generate(asset_type, 0)
        assert str(exc.value) == "purchase_number 必须 >= 1"

    def test_type_path_unknown_for_none(self):
        """空类型 → UNKNOWN 前缀"""
        code = AssetCodeGenerator.generate(None)[0]
        assert code.startswith("UNKNOWN-")

    def test_type_path_truncates_at_depth_10(self, db):
        """11 层类型链: 路径精确截断为前 10 层并以 - 连接"""
        parent = None
        leaf = None
        for i in range(1, 12):
            leaf = AssetType.objects.create(type_code=f"L{i:02d}", type_name=f"层{i}", parent=parent)
            parent = leaf
        path = AssetCodeGenerator._get_type_path(leaf)
        # 遍历自叶向根,max_depth 截断的是根侧 → 保留 L02..L11 共 10 层
        expected = "-".join(f"L{i:02d}" for i in range(2, 12))
        assert path == expected

    def test_unique_check_retry_limit_and_message(self, asset_type, db):
        """持续冲突: 恰好重试 MAX_RETRY(3) 次后抛错且文案逐字"""
        fixed_hex = "DEADBEEF"
        with mock.patch.object(AssetCodeGenerator, "_generate_uuid_hex", return_value=fixed_hex) as mock_gen:
            Asset.objects.create(
                asset_code=f"AT001-{fixed_hex}",
                asset_name="占用",
                asset_purchase_price=1,
                asset_purchase_date="2024-01-01",
                asset_entry_date="2024-01-01",
                asset_type_recordcode=asset_type,
            )
            with pytest.raises(RuntimeError) as exc:
                AssetCodeGenerator.generate_with_unique_check(asset_type, 1)
        assert mock_gen.call_count == 3
        assert str(exc.value) == "生成资产编码失败:连续 3 次尝试均存在唯一性冲突"

    def test_unique_check_detects_existing_collision(self, asset_type, db):
        """唯一性检查真实生效: 冲突时换码成功而非原样返回"""
        fixed_hex = "CAFEBABE"
        with mock.patch.object(AssetCodeGenerator, "_generate_uuid_hex", side_effect=[fixed_hex, "FFEEDDCC"]):
            Asset.objects.create(
                asset_code=f"AT001-{fixed_hex}",
                asset_name="占用",
                asset_purchase_price=1,
                asset_purchase_date="2024-01-01",
                asset_entry_date="2024-01-01",
                asset_type_recordcode=asset_type,
            )
            codes = AssetCodeGenerator.generate_with_unique_check(asset_type, 1)
        assert codes[0] == "AT001-FFEEDDCC"


@pytest.mark.django_db
class TestImmutableFieldsKill:
    """不可变字段集逐字段禁改(杀伤 frozenset 字符串变异)"""

    @pytest.mark.parametrize(
        "field",
        ["recordcode", "qr_code", "version", "is_deleted", "created_at", "updated_at", "asset_current_status"],
    )
    def test_immutable_field_rejected_with_exact_detail(self, asset, admin_auth_user, field):
        with pytest.raises(AppValidationError) as exc:
            AssetService.update_asset(asset_code="A001", update_data={field: "HACKED"}, user=admin_auth_user)
        assert exc.value.error_code == "FIELD_NOT_ALLOWED"
        assert exc.value.detail == f"不允许修改字段: {field}"


@pytest.mark.django_db
class TestCreateAssetKills:
    """create_asset: 默认批数/qr_code JSON"""

    def _data(self):
        return {
            "asset_name": "新资产",
            "asset_purchase_price": 100,
            "asset_purchase_date": "2024-01-01",
            "asset_entry_date": "2024-01-02",
            "asset_type_recordcode": AssetType.objects.get(type_code="AT001"),
        }

    def test_create_default_purchase_number_is_one(self, asset_type, db):
        """未传 asset_purchase_number: 只建 1 条"""
        created = AssetService.create_asset(self._data())
        assert len(created) == 1

    def test_qr_code_json_payload_exact(self, asset_type, db):
        """自动生成 qr_code: JSON 键值逐字"""
        created = AssetService.create_asset(self._data())
        payload = json.loads(created[0].qr_code)
        assert payload == {"asset_code": created[0].asset_code, "scan_type": "asset_detail"}

    def test_preset_qr_code_preserved(self, asset_type, db):
        """调用方预设 qr_code: 不被覆盖"""
        data = self._data()
        data["qr_code"] = "preset-value"
        created = AssetService.create_asset(data)
        assert created[0].qr_code == "preset-value"


@pytest.mark.django_db
class TestErrorDetailKills:
    """错误文案逐字断言"""

    def test_update_not_found_detail(self, admin_auth_user):
        with pytest.raises(AppValidationError) as exc:
            AssetService.update_asset(asset_code="NOPE", update_data={"asset_name": "x"}, user=admin_auth_user)
        assert exc.value.detail == "资产 NOPE 不存在"

    def test_delete_not_in_store_detail(self, asset, admin_auth_user):
        """in_use 资产删除: 文案逐字"""
        asset.asset_current_status = "in_use"
        asset.save(update_fields=["asset_current_status"])
        with pytest.raises(AppValidationError) as exc:
            AssetService.delete_asset(asset_code="A001", user=admin_auth_user)
        assert exc.value.detail == "资产当前状态为 in_use,不允许删除"

    def test_delete_with_outasset_detail(self, asset, admin_auth_user, db):
        """in_store 但存在出库记录: 文案逐字"""
        OutAsset.objects.create(asset_recordcode=asset, outasset_date="2024-01-01")
        with pytest.raises(AppValidationError) as exc:
            AssetService.delete_asset(asset_code="A001", user=admin_auth_user)
        assert exc.value.detail == f"资产 {asset.asset_code} 存在未完成的出库记录"

    def test_delete_with_damaged_detail(self, asset, admin_auth_user, db):
        """存在待报废记录: 文案逐字"""
        DamagedAsset.objects.create(asset_recordcode=asset, damaged_asset_number=1, original_status="in_store")
        with pytest.raises(AppValidationError) as exc:
            AssetService.delete_asset(asset_code="A001", user=admin_auth_user)
        assert exc.value.detail == "资产存在待报废记录,不允许删除"

    def test_change_status_invalid_value_detail(self, asset, admin_auth_user):
        with pytest.raises(AppValidationError) as exc:
            AssetService.change_asset_status(asset_code="A001", new_status="bogus", user=admin_auth_user)
        assert exc.value.detail == "无效的资产状态: bogus"

    def test_change_status_not_found_detail(self, admin_auth_user):
        with pytest.raises(AppValidationError) as exc:
            AssetService.change_asset_status(asset_code="NOPE", new_status="in_use", user=admin_auth_user)
        assert exc.value.detail == "资产 NOPE 不存在"

    def test_change_employee_not_found_detail(self, asset, admin_auth_user):
        with pytest.raises(NotFoundError) as exc:
            AssetService.change_outasset_employee(
                asset_code="A001",
                applicant_jobcode="GHOST1",
                manager_jobcode="U002",
                user=admin_auth_user,
            )
        assert exc.value.detail == "员工 GHOST1 不存在"

    def test_change_manager_not_found_detail(self, asset, employee, admin_auth_user):
        with pytest.raises(NotFoundError) as exc:
            AssetService.change_outasset_employee(
                asset_code="A001",
                applicant_jobcode=employee.employee_jobcode,
                manager_jobcode="GHOST2",
                user=admin_auth_user,
            )
        assert exc.value.detail == "员工 GHOST2 不存在"


@pytest.mark.django_db
class TestAuditSnapshotKills:
    """审计快照键值与状态日志逐字断言"""

    def test_change_status_state_log_exact(self, asset, admin_auth_user):
        """手动改状态: before/after/触发词逐字"""
        AssetService.change_asset_status(
            asset_code="A001",
            new_status="broken",
            operator_jobcode="adminuser",
            operator_name="管理员",
            user=admin_auth_user,
        )
        log = AssetOperationLog.objects.get(asset_code="A001", operation_type="state_change")
        assert log.description == "状态从 in_store 变更为 broken (触发: manual_change)"
        assert log.before_data == {"asset_current_status": "in_store"}
        assert log.after_data == {"asset_current_status": "broken"}

    def test_change_employee_snapshot_exact(self, asset, user, employee, admin_auth_user):
        """换使用人/保管人: before/after 快照键与值精确"""
        asset.asset_applicant_recordcode = user
        asset.asset_manager_recordcode = user
        asset.save(update_fields=["asset_applicant_recordcode", "asset_manager_recordcode"])

        AssetService.change_outasset_employee(
            asset_code="A001",
            applicant_jobcode=employee.employee_jobcode,
            manager_jobcode=employee.employee_jobcode,
            user=admin_auth_user,
        )
        log = AssetOperationLog.objects.filter(asset_code="A001", operation_type="update").last()
        assert set(log.before_data.keys()) == {"asset_applicant", "asset_manager"}
        assert set(log.after_data.keys()) == {"asset_applicant", "asset_manager"}
        assert log.before_data["asset_applicant"] == str(user)
        assert log.after_data == {
            "asset_applicant": employee.employee_jobcode,
            "asset_manager": employee.employee_jobcode,
        }
        assert log.after_data["asset_manager"] == employee.employee_jobcode


@pytest.mark.django_db
class TestQrImageKills:
    """二维码图片: 扫码 URL 与构造参数"""

    def test_qr_payload_url_and_constructor_args(self, asset):
        """扫码 URL 逐字 + QRCode 构造参数精确 + PNG 魔数"""
        import qrcode

        captured = {}
        real_qrcode_cls = qrcode.QRCode

        def spy_qrcode(*args, **kwargs):
            captured["kwargs"] = kwargs
            qr = real_qrcode_cls(*args, **kwargs)
            real_add = qr.add_data

            def add_data(data):
                captured["url"] = data
                return real_add(data)

            qr.add_data = add_data
            return qr

        with mock.patch.object(qrcode, "QRCode", side_effect=spy_qrcode):
            png = AssetService.generate_qr_code_image(asset, "http://testserver")

        assert captured["kwargs"]["version"] == 1
        assert captured["kwargs"]["box_size"] == 10
        assert captured["kwargs"]["border"] == 4
        assert captured["url"] == f"http://testserver/scan/{asset.recordcode}/"
        # buffer.seek(1) 变异会使 PNG 魔数错位
        assert png.startswith(b"\x89PNG")


@pytest.mark.django_db
class TestAtomicRollbackKills:
    """中途审计失败全量回滚(杀伤 @transaction.atomic 删除变异)"""

    def test_create_asset_rolls_back_on_audit_failure(self, asset_type, db):
        from apps.assetmanagement.audit import AuditLogger

        data = {
            "asset_name": "回滚资产",
            "asset_purchase_price": 1,
            "asset_purchase_date": "2024-01-01",
            "asset_entry_date": "2024-01-02",
            "asset_type_recordcode": asset_type,
            "asset_purchase_number": 2,
        }
        with mock.patch.object(AuditLogger, "log_asset_create", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                AssetService.create_asset(data)
        assert Asset.objects.filter(asset_name="回滚资产").count() == 0

    def test_update_asset_rolls_back_on_audit_failure(self, asset, admin_auth_user):
        from apps.assetmanagement.audit import AuditLogger

        with mock.patch.object(AuditLogger, "log_asset_update", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                AssetService.update_asset(asset_code="A001", update_data={"asset_name": "已改"}, user=admin_auth_user)
        asset.refresh_from_db()
        assert asset.asset_name == "测试资产"

    def test_change_status_rolls_back_on_audit_failure(self, asset, admin_auth_user):
        from apps.assetmanagement.audit import AuditLogger

        with mock.patch.object(AuditLogger, "log_state_change", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                AssetService.change_asset_status(asset_code="A001", new_status="broken", user=admin_auth_user)
        asset.refresh_from_db()
        assert asset.asset_current_status == "in_store"

    def test_delete_asset_rolls_back_on_audit_failure(self, asset, admin_auth_user):
        from apps.assetmanagement.audit import AuditLogger

        with mock.patch.object(AuditLogger, "log_asset_delete", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                AssetService.delete_asset(asset_code="A001", user=admin_auth_user)
        assert Asset.objects.filter(asset_code="A001").exists()
