"""【MA-12】AuthUserViewSet 类属性死闸门治理回归。

两步法约束：类属性置 .none() 作旁路守卫，真实取行口径迁入 get_queryset()
（返回 AuthUser.objects.all()，读路径行为逐字等价）。
"""

from apps.authusermanagement.models import AuthUser
from apps.authusermanagement.views import AuthUserViewSet


def test_queryset_gate_and_single_entry(db, auth_user):
    """库内有行时：类属性闸门取不到行（修复前为真实全量 qs，此处先红），
    get_queryset() 与原类属性逐字等价、可取到行。"""
    assert AuthUser.objects.exists()
    assert not AuthUserViewSet.queryset.exists()
    assert AuthUserViewSet().get_queryset().exists()
