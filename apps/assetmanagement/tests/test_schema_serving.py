"""【BF-109 / AUD-10】文档端点认证收紧测试

drf-spectacular 默认 SERVE_PERMISSIONS=AllowAny, 修复后改为 IsAuthenticated
(config/settings/base.py SPECTACULAR_SETTINGS)。

匿名请求预期 401 而非 403: SERVE_AUTHENTICATION 未设置 → 回落
DEFAULT_AUTHENTICATION_CLASSES(JWTCookieAuthentication), 其
authenticate_header 返回 'Bearer realm="api"'(simplejwt JWTAuthentication,
AUTH_HEADER_TYPES=("Bearer",)) → DRF handle_exception 对非空挑战头保持
401 + WWW-Authenticate, 仅挑战头为空才降级 403。
"""

import pytest
from django.urls import reverse
from rest_framework import status


@pytest.mark.django_db
class TestSchemaServingPermissions:
    def test_anonymous_swagger_returns_401_with_challenge(self, api_client):
        """匿名 GET /swagger/ → 401 且带 Bearer 挑战头(非 403)"""
        response = api_client.get(reverse("swagger-ui-v1"))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Bearer" in response["WWW-Authenticate"]

    def test_anonymous_redoc_returns_401(self, api_client):
        """匿名 GET /redoc/ → 401"""
        response = api_client.get(reverse("redoc-v1"))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_anonymous_schema_returns_401(self, api_client):
        """匿名 GET /schema/ → 401"""
        response = api_client.get(reverse("schema-v1"))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_authenticated_swagger_returns_200(self, api_client, admin_auth_user):
        """登录态 GET /swagger/ → 200(Swagger UI HTML)"""
        api_client.force_authenticate(user=admin_auth_user)
        response = api_client.get(reverse("swagger-ui-v1"))
        assert response.status_code == status.HTTP_200_OK

    def test_authenticated_schema_returns_200(self, api_client, admin_auth_user):
        """登录态 GET /schema/ → 200(OpenAPI 3 JSON)"""
        api_client.force_authenticate(user=admin_auth_user)
        response = api_client.get(reverse("schema-v1"))
        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"].startswith("application/vnd.oai.openapi")

    def test_anonymous_business_endpoint_401_carries_challenge(self, api_client):
        """【BF-109 附带修复回归】自定义全局异常处理器重包时透传 DRF 原生响应头——
        业务端点匿名 401 同样须携带 WWW-Authenticate(RFC 6750), 不只文档端点"""
        response = api_client.get(reverse("assets-list"))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Bearer" in response["WWW-Authenticate"]
