"""M-LAY-03: Department.save 不依赖 DepartmentService 私有成员。"""

import sys
from unittest.mock import patch

import pytest
from django.core.cache import cache

from apps.usermanagement.models import Department
from apps.usermanagement.utils.department_cache import descendants_cache_key


@pytest.mark.django_db
def test_save_does_not_import_department_service():
    parent = Department(
        department_code="MLAY03-P",
        department_name="分层父部门",
        path="/ROOT",
        level=0,
    )
    parent.save()
    child = Department(
        department_code="MLAY03-C",
        department_name="分层子部门",
        path="/ROOT/CHILD",
        level=1,
    )
    cache.set(descendants_cache_key(parent.recordcode), ["stale"])
    cache.set(descendants_cache_key(child.recordcode), ["stale"])

    with patch.dict(sys.modules, {"apps.usermanagement.services.department_service": None}):
        child.save()

    assert cache.get(descendants_cache_key(parent.recordcode)) is None
    assert cache.get(descendants_cache_key(child.recordcode)) is None
