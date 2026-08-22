"""
员工管理服务层,封装员工的 CRUD、认证账号绑定/解绑等核心业务逻辑

类:
  - EmployeeService: 员工服务(所有写操作 @transaction.atomic)

函数/方法:
  - bind_auth_user: 绑定认证账号到员工(含冲突检测)
  - unbind_auth_user: 解绑员工的认证账号
  - replace_auth_user: 原子替换员工的认证账号
  - create_employee: 创建员工(含工号唯一性校验)
  - change_employee_status: 更改员工状态
  - batch_create_employee: 批量创建员工(逐条执行,返回详情)
  - batch_delete_employee: 批量删除员工(含关联资产预检查)

调用链:
  本模块被 views/employee_view.py 调用
  本模块依赖 models.Employee、employee_audit_adapter.EmployeeAuditAdapter
"""

import copy
from typing import Any

from django.db import transaction

from apps.usermanagement.employee_audit_adapter import EmployeeAuditAdapter
from apps.usermanagement.models import Employee
from core.constants import MAX_BATCH_SIZE
from core.exceptions import AppValidationError, BusinessLogicError


class EmployeeService:
    """
    员工服务
    """

    @staticmethod
    @transaction.atomic
    def bind_auth_user(
        employee_jobcode: str,
        auth_username: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> Employee:
        """
        绑定认证账号到员工

        前置校验:
        - 员工必须存在且未删除
        - 员工当前未绑定 auth_user
        - 目标 auth_user 存在且未删除
        - 目标 auth_user 未绑定到其他员工

        Args:
            employee_jobcode: 员工工号
            auth_username: 认证账号用户名
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名

        Returns:
            绑定后的员工实例

        Raises:
            AppValidationError: 员工或认证账号不存在
            BusinessLogicError: 绑定冲突
        """
        from apps.authusermanagement.models import AuthUser

        # 锁定目标员工
        employee = Employee.objects.select_for_update().get(employee_jobcode=employee_jobcode, is_deleted=False)

        if employee.auth_user_id is not None:
            raise BusinessLogicError(
                detail="该员工已绑定认证账号,请先解绑",
                error_code="EMPLOYEE_ALREADY_BOUND",
            )

        # 获取目标认证账号
        try:
            auth_user = AuthUser.objects.select_for_update().get(
                auth_username=auth_username,
            )
        except AuthUser.DoesNotExist:
            raise AppValidationError(
                detail=f"认证账号 {auth_username} 不存在",
                error_code="AUTH_USER_NOT_FOUND",
            )

        # 检查目标认证账号是否已绑定到其他员工
        existing_binding = (
            Employee.objects.filter(auth_user=auth_user, is_deleted=False)
            .exclude(employee_jobcode=employee_jobcode)
            .first()
        )
        if existing_binding:
            raise BusinessLogicError(
                detail=f"认证账号 {auth_username} 已绑定到员工 {existing_binding.employee_jobcode}",
                error_code="AUTH_USER_ALREADY_BOUND",
            )

        # 执行绑定
        employee.auth_user = auth_user
        employee.save(update_fields=["auth_user", "updated_at"])

        EmployeeAuditAdapter.log_bind_auth_user(employee, auth_username, operator_jobcode, operator_name)

        return employee

    @staticmethod
    @transaction.atomic
    def unbind_auth_user(
        employee_jobcode: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> Employee:
        """
        解绑员工的认证账号

        前置校验:
        - 员工必须存在且未删除
        - 员工当前已绑定 auth_user

        注意:解绑后 AuthUser 权限保留(auth_user 可能是 API 账号)。

        Args:
            employee_jobcode: 员工工号
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名

        Returns:
            解绑后的员工实例

        Raises:
            AppValidationError: 员工不存在
            BusinessLogicError: 员工未绑定认证账号
        """
        employee = Employee.objects.select_for_update().get(employee_jobcode=employee_jobcode, is_deleted=False)

        if employee.auth_user_id is None:
            raise BusinessLogicError(
                detail="该员工未绑定认证账号",
                error_code="EMPLOYEE_NOT_BOUND",
            )

        old_auth_username = employee.auth_user.auth_username

        # 执行解绑(AuthUser 权限保留)
        employee.auth_user = None
        employee.save(update_fields=["auth_user", "updated_at"])

        EmployeeAuditAdapter.log_unbind_auth_user(employee, old_auth_username, operator_jobcode, operator_name)

        return employee

    @staticmethod
    @transaction.atomic
    def replace_auth_user(
        employee_jobcode: str,
        new_auth_username: str,
        operator_jobcode: str | None = None,
        operator_name: str | None = None,
    ) -> Employee:
        """
        替换员工的认证账号(原子操作:解绑旧 + 绑定新)

        前置校验:
        - 员工必须存在且未删除
        - 新 auth_user 存在且未删除
        - 新 auth_user 未绑定到其他员工

        Args:
            employee_jobcode: 员工工号
            new_auth_username: 新认证账号用户名
            operator_jobcode: 操作人工号
            operator_name: 操作人姓名

        Returns:
            替换后的员工实例

        Raises:
            AppValidationError: 员工或认证账号不存在
            BusinessLogicError: 替换冲突
        """
        from apps.authusermanagement.models import AuthUser

        # 锁定目标员工
        employee = Employee.objects.select_for_update().get(employee_jobcode=employee_jobcode, is_deleted=False)

        old_auth_username = employee.auth_user.auth_username if employee.auth_user else None

        # H3 修复:检查新账号是否与当前绑定相同
        if employee.auth_user and employee.auth_user.auth_username == new_auth_username:
            raise AppValidationError(
                detail="新认证账号与当前绑定相同",
                error_code="AUTH_USER_SAME",
            )

        # 获取新认证账号
        try:
            new_auth_user = AuthUser.objects.select_for_update().get(
                auth_username=new_auth_username,
            )
        except AuthUser.DoesNotExist:
            raise AppValidationError(
                detail=f"认证账号 {new_auth_username} 不存在",
                error_code="AUTH_USER_NOT_FOUND",
            )

        # 检查新认证账号是否已绑定到其他员工
        existing_binding = (
            Employee.objects.filter(auth_user=new_auth_user, is_deleted=False)
            .exclude(employee_jobcode=employee_jobcode)
            .first()
        )
        if existing_binding:
            raise BusinessLogicError(
                detail=f"认证账号 {new_auth_username} 已绑定到员工 {existing_binding.employee_jobcode}",
                error_code="AUTH_USER_ALREADY_BOUND",
            )

        # 执行替换(原子操作)
        employee.auth_user = new_auth_user
        employee.save(update_fields=["auth_user", "updated_at"])

        EmployeeAuditAdapter.log_replace_auth_user(
            employee, old_auth_username, new_auth_username, operator_jobcode, operator_name
        )

        return employee

    @staticmethod
    @transaction.atomic
    def create_employee(employee_data: dict[str, Any]) -> Employee:
        """
        创建员工

        Args:
            employee_data: 员工数据

        Returns:
            创建的员工实例
        """
        if Employee.objects.filter(employee_jobcode=employee_data["employee_jobcode"]).exists():
            raise AppValidationError(
                detail=f"工号 {employee_data['employee_jobcode']} 已存在", error_code="DUPLICATE_EMPLOYEE_JOBCODE"
            )

        employee = Employee.objects.create(**employee_data)
        EmployeeAuditAdapter.log_create(
            employee, employee_data.get("operator_jobcode"), employee_data.get("operator_name")
        )
        return employee

    # 【AGENTS 规范 - P2-09】get_employee_by_jobcode 已删除,
    # 与 EmployeeSelector.get_employee_by_jobcode 完全重复,调用方请改用 EmployeeSelector

    @staticmethod
    @transaction.atomic
    def change_employee_status(employee: Employee, new_status: str) -> Employee:
        """
        更改员工状态

        【AGENTS 规范 - P1-10】供 EmployeeViewSet.change_status 使用,
        将状态变更逻辑从视图层迁移到 Service 层,确保业务逻辑内聚

        Args:
            employee: 员工实例
            new_status: 新状态值,必须是 Employee.EMPLOYEE_STATUS_CHOICES 中的有效值

        Returns:
            更新后的员工实例

        Raises:
            ValidationError: 当 new_status 不是合法状态值时
        """
        valid_statuses = dict(Employee.EMPLOYEE_STATUS_CHOICES)
        if new_status not in valid_statuses:
            raise AppValidationError(
                detail=f"无效的员工状态: {new_status},有效值为 {list(valid_statuses.keys())}",
                error_code="INVALID_EMPLOYEE_STATUS",
            )

        # C1 修复:先记录旧状态,再赋新值
        old_status = employee.employee_status
        employee.employee_status = new_status
        employee.save(update_fields=["employee_status"])
        EmployeeAuditAdapter.log_state_change(employee, old_status, new_status)
        return employee

    @staticmethod
    def batch_create_employee(employee_data_list: list[dict[str, Any]]) -> dict[str, Any]:
        """
        批量创建员工(逐条独立执行,返回详细结果)

        【P0-优化】错误码映射机制:
        - 单条创建方法(create_employee)中的验证异常均携带 error_code 属性
        - 批量方法通过 e.error_code 直接读取,不再使用字符串匹配
        - 若单条方法未设置 error_code,则兜底使用 "VALIDATION_ERROR"

        复用 EmployeeService.create_employee() 单条创建逻辑。
        使用 copy.deepcopy 避免原始数据被修改。
        """
        if len(employee_data_list) > MAX_BATCH_SIZE:
            raise AppValidationError(
                detail=f"单次批量创建不能超过 {MAX_BATCH_SIZE} 条", error_code="BATCH_SIZE_EXCEEDED"
            )

        success_items: list[Employee] = []
        fail_items: list[dict[str, Any]] = []

        for idx, employee_data in enumerate(employee_data_list):
            try:
                result = EmployeeService.create_employee(employee_data=copy.deepcopy(employee_data))
                success_items.append(result)
            except AppValidationError as e:
                fail_items.append(
                    {
                        "index": idx,
                        "row_number": employee_data.get("row_number"),
                        "input_data": employee_data,
                        "error_code": e.error_code or "VALIDATION_ERROR",
                        "error_message": str(e.detail),
                    }
                )
            except Exception:
                fail_items.append(
                    {
                        "index": idx,
                        "row_number": employee_data.get("row_number"),
                        "input_data": employee_data,
                        "error_code": "INTERNAL_ERROR",
                        "error_message": "服务器内部错误,请稍后重试",
                    }
                )

        return {
            "total": len(employee_data_list),
            "success_count": len(success_items),
            "fail_count": len(fail_items),
            "success_items": success_items,
            "fail_items": fail_items,
        }

    @staticmethod
    def batch_delete_employee(employee_jobcodes: list[str]) -> dict[str, Any]:
        """
        批量删除员工(软删除,逐条独立执行)

        【优化】批量预检查关联资产,减少数据库查询次数

        前置校验:
        - 员工必须存在
        - 员工不存在关联资产记录(作为申请人/保管人)
        """
        from apps.assetmanagement.models import Asset

        if len(employee_jobcodes) > MAX_BATCH_SIZE:
            raise AppValidationError(
                detail=f"单次批量删除不能超过 {MAX_BATCH_SIZE} 条", error_code="BATCH_SIZE_EXCEEDED"
            )

        success_ids: list[str] = []
        fail_items: list[dict[str, Any]] = []

        # 批量预检查:一次查询所有员工
        existing_employees = {
            emp.employee_jobcode: emp for emp in Employee.objects.filter(employee_jobcode__in=employee_jobcodes)
        }

        # 批量预检查:一次查询所有关联资产的员工
        # 【修复】FK to_field="recordcode",需提取 recordcode 而非模型实例
        employees_with_assets = set()
        if existing_employees:
            # 提取所有员工的 recordcode(FK 存储的是 recordcode 字符串)
            recordcodes = [emp.recordcode for emp in existing_employees.values() if emp.recordcode]

            # 查询作为申请人的员工 recordcode
            applicant_recordcodes = Asset.objects.filter(
                asset_applicant_recordcode__in=recordcodes, is_deleted=False
            ).values_list("asset_applicant_recordcode", flat=True)
            employees_with_assets.update(applicant_recordcodes)

            # 查询作为保管人的员工 recordcode
            manager_recordcodes = Asset.objects.filter(
                asset_manager_recordcode__in=recordcodes, is_deleted=False
            ).values_list("asset_manager_recordcode", flat=True)
            employees_with_assets.update(manager_recordcodes)

        # 逐条处理删除
        for jobcode in employee_jobcodes:
            try:
                employee = existing_employees.get(jobcode)
                if not employee or employee.is_deleted:
                    fail_items.append(
                        {"id": jobcode, "error_code": "NOT_FOUND", "error_message": f"员工 {jobcode} 不存在或已删除"}
                    )
                    continue

                # 检查关联资产(通过 recordcode 匹配)
                if employee.recordcode in employees_with_assets:
                    fail_items.append(
                        {
                            "id": jobcode,
                            "error_code": "HAS_RELATED_ASSETS",
                            "error_message": "员工存在关联资产记录,不允许删除",
                        }
                    )
                    continue

                with transaction.atomic():
                    employee.delete()
                EmployeeAuditAdapter.log_delete(employee.employee_jobcode, employee.employee_name)
                success_ids.append(jobcode)

            except Exception:
                fail_items.append(
                    {"id": jobcode, "error_code": "INTERNAL_ERROR", "error_message": "服务器内部错误,请稍后重试"}
                )

        return {
            "total": len(employee_jobcodes),
            "success_count": len(success_ids),
            "fail_count": len(fail_items),
            "success_ids": success_ids,
            "fail_items": fail_items,
        }
