"""
批量操作 API 契约快照测试（DR-1 重构回归屏障，CT-4）

锁定以下契约，防止 DR-1 收敛（batch_mixins 复用 / ViewSet 基类提取 /
BatchResponseHelper 引入）过程中发生行为漂移：
- 响应 data 的键名集合与类型
- message 文案逐字一致
- fail_items 条目结构（index/row_number/input_data/error_code/error_message）

若本文件任何断言在重构后失败, 说明 API 契约被破坏, 必须回滚。
"""

import pytest
from django.urls import reverse
from rest_framework import status


@pytest.fixture
def authenticated_client(api_client, auth_user):
    """已认证的用户客户端"""
    api_client.force_authenticate(user=auth_user)
    return api_client


@pytest.fixture
def admin_authenticated_client(api_client, admin_auth_user):
    """管理员用户客户端"""
    api_client.force_authenticate(user=admin_auth_user)
    return api_client


@pytest.mark.django_db
class TestLifecycleBatchContract:
    """资产生命周期批量接口契约快照（BrokenAsset 代表三胞胎）"""

    def test_batch_delete_contract(self, admin_authenticated_client, broken_asset):
        """批量删除: 锁定 data 键集、计数语义与 message 文案"""
        url = reverse("broken-assets-batch-delete")
        response = admin_authenticated_client.post(
            url, {"ids": [broken_asset.recordcode]}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0

        data = response.data["data"]
        # 键集合精确匹配(多键/少键均视为契约破坏)
        assert set(data.keys()) == {
            "total", "success_count", "fail_count", "success_ids", "fail_items",
        }
        assert data["total"] == 1
        assert data["success_count"] == 1
        assert data["fail_count"] == 0
        assert data["success_ids"] == [broken_asset.recordcode]
        assert data["fail_items"] == []
        # message 文案逐字锁定
        assert response.data["message"] == "Batch delete done: 1 success, 0 fail"

    def test_batch_delete_not_found_contract(self, admin_authenticated_client):
        """批量删除含不存在记录时 fail_items 条目结构锁定"""
        url = reverse("broken-assets-batch-delete")
        response = admin_authenticated_client.post(
            url, {"ids": ["NO_SUCH_RECORDCODE"]}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert data["success_count"] == 0
        assert data["fail_count"] == 1
        fail_item = data["fail_items"][0]
        assert set(fail_item.keys()) == {"id", "error_code", "error_message"}
        assert fail_item["error_code"] == "NOT_FOUND"
        assert fail_item["error_message"] == "Record not found"

    def test_by_asset_contract(self, admin_authenticated_client, asset, broken_asset):
        """by_asset 查询: 锁定成功与 404 的 message 文案"""
        url = reverse(
            "broken-assets-by-asset", kwargs={"asset_code": asset.asset_code}
        )
        response = admin_authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "查询成功"

        missing_url = reverse(
            "broken-assets-by-asset", kwargs={"asset_code": "NO_SUCH_ASSET"}
        )
        missing = admin_authenticated_client.get(missing_url)
        assert missing.status_code == status.HTTP_404_NOT_FOUND
        assert missing.data["message"] == f"资产 NO_SUCH_ASSET 不存在"


@pytest.mark.django_db
class TestEmployeeBatchContract:
    """员工批量接口(View 层)契约快照"""

    valid_employee_payload = {
        "employee_jobcode": "T99999",
        "employee_name": "契约测试员工",
        "employee_phone": "13800000000",
        "employee_location": "测试位置",
        "employee_status": "active",
        "employee_department_code": None,
        "employee_description": "",
        "sort_order": 0,
    }

    def test_batch_create_contract(
        self, admin_authenticated_client, department, admin_auth_user
    ):
        """批量创建: 键集合 + 动态 message 文案 + fail_items 结构锁定"""
        item = dict(self.valid_employee_payload)
        item["employee_department_code"] = department.department_code
        url = reverse("employees-batch-create")
        response = admin_authenticated_client.post(url, {"items": [item]}, format="json")
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["code"] == 0

        data = response.data["data"]
        assert set(data.keys()) == {
            "total", "success_count", "fail_count", "success_items", "fail_items",
        }
        assert data["total"] == 1
        assert data["success_count"] == 1
        assert isinstance(data["success_items"], list)
        # message 为动态文案, 逐字锁定格式
        assert response.data["message"] == "批量创建完成,成功 1 条,失败 0 条"

    def test_batch_create_fail_item_structure(
        self, admin_authenticated_client, department
    ):
        """校验失败条目的五字段结构锁定(index/row_number/input_data/error_code/error_message)"""
        # 先创建同工号员工, 触发 DUPLICATE_EMPLOYEE_JOBCODE 失败分支
        from apps.usermanagement.models import Employee

        Employee.objects.create(
            employee_jobcode="T99999",
            employee_name="已存在员工",
            employee_phone="13900000000",
            employee_location="测试位置",
            employee_status="active",
            sort_order=0,
        )
        bad = dict(self.valid_employee_payload)
        # 【已知存量缺陷, 不在本 DR-1 范围内修复】
        # 当失败条目携带 employee_department_code 时, validated_data 中的
        # employee_department 为 Department 模型对象, input_data 原样进入
        # fail_items 导致响应 JSON 渲染抛 TypeError(500)。
        # 本测试规避该场景(不传部门), 缺陷已单独登记待修。
        bad.pop("employee_department_code", None)
        url = reverse("employees-batch-create")
        response = admin_authenticated_client.post(url, {"items": [bad]}, format="json")
        assert response.status_code == status.HTTP_200_OK

        data = response.data["data"]
        assert data["fail_count"] == 1
        fail_item = data["fail_items"][0]
        assert set(fail_item.keys()) == {
            "index", "row_number", "input_data", "error_code", "error_message",
        }
        assert fail_item["error_code"] not in (None, "")
