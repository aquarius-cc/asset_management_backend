"""
安全头配置一致性测试

验证"安全头单一来源 = Nginx 边缘层"架构决策:
1. 生产环境 Django 不下发任何安全响应头(HSTS/nosniff/frame-options/referrer)
2. Nginx tpl 中无已弃用的 X-XSS-Protection
3. Nginx tpl 中所有代理路径均有 proxy_hide_header 防御护栏

参见: config/settings/production.py 安全头治理注释
"""

from pathlib import Path


_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


def _read_production_py() -> str:
    return (_BACKEND_ROOT / "config" / "settings" / "production.py").read_text(encoding="utf-8")


def _read_nginx_tpl() -> str:
    return (_BACKEND_ROOT / "docker" / "nginx" / "conf.d" / "default.conf.tpl").read_text(encoding="utf-8")


# === Django 配置断言(文件级, 无需导入 production 模块) ===


class TestProductionSecurityHeadersDisabled:
    """production.py 中安全头必须显式关闭(由 Nginx 唯一下发)"""

    def test_hsts_disabled(self):
        src = _read_production_py()
        assert "SECURE_HSTS_SECONDS = 0" in src, (
            "production.py 缺少 SECURE_HSTS_SECONDS = 0"
        )

    def test_hsts_subdomains_disabled(self):
        src = _read_production_py()
        assert "SECURE_HSTS_INCLUDE_SUBDOMAINS = False" in src

    def test_hsts_preload_disabled(self):
        src = _read_production_py()
        assert "SECURE_HSTS_PRELOAD = False" in src

    def test_content_type_nosniff_disabled(self):
        src = _read_production_py()
        assert "SECURE_CONTENT_TYPE_NOSNIFF = False" in src, (
            "production.py 缺少 SECURE_CONTENT_TYPE_NOSNIFF = False"
        )

    def test_referrer_policy_disabled(self):
        src = _read_production_py()
        assert 'SECURE_REFERRER_POLICY = ""' in src, (
            "production.py 缺少 SECURE_REFERRER_POLICY = \"\""
        )

    def test_xframe_options_middleware_removed(self):
        src = _read_production_py()
        assert "XFrameOptionsMiddleware" in src, (
            "production.py 中未找到 XFrameOptionsMiddleware 过滤逻辑"
        )
        # 验证是通过列表推导移除, 而非注释掉
        assert 'm for m in MIDDLEWARE if m != "django.middleware.clickjacking.XFrameOptionsMiddleware"' in src


# === Nginx 模板断言 ===


def _read_nginx_tpl() -> str:
    """读取 nginx 配置模板"""
    tpl_path = Path(__file__).resolve().parent.parent.parent.parent / "docker" / "nginx" / "conf.d" / "default.conf.tpl"
    if not tpl_path.exists():
        # fallback: 从 asset_management_backend 根目录查找
        tpl_path = Path(__file__).resolve().parent.parent.parent / "docker" / "nginx" / "conf.d" / "default.conf.tpl"
    return tpl_path.read_text(encoding="utf-8")


class TestNginxSecurityHeaders:
    """Nginx 安全头配置断言"""

    def test_no_x_xss_protection(self):
        """X-XSS-Protection 已弃用, 必须从 tpl 中完全删除"""
        content = _read_nginx_tpl()
        assert "X-XSS-Protection" not in content, (
            "default.conf.tpl 中仍包含已弃用的 X-XSS-Protection, 必须删除"
        )

    def test_server_level_has_all_security_headers(self):
        """server 级必须包含全部 5 个安全头(唯一事实来源)"""
        content = _read_nginx_tpl()
        required = [
            "Strict-Transport-Security",
            "X-Content-Type-Options",
            "X-Frame-Options",
            "Referrer-Policy",
            "Permissions-Policy",
        ]
        for header in required:
            assert f"add_header {header}" in content, (
                f"server 级缺少 add_header {header}"
            )

    def test_proxy_locations_have_hide_headers(self):
        """所有代理 location 必须有 proxy_hide_header 防御护栏"""
        content = _read_nginx_tpl()
        proxy_locations = ["/api/", "/api/v1/auth/token/", "/ws/", "/health/", "/ready/"]
        headers_to_hide = [
            "Strict-Transport-Security",
            "X-Content-Type-Options",
            "X-Frame-Options",
            "Referrer-Policy",
            "Permissions-Policy",
        ]
        for location in proxy_locations:
            # 找到 location 块
            marker = f"location {location}"
            assert marker in content, f"tpl 中缺少 location {location}"
            # 找到该 location 块的起始位置
            start = content.index(marker)
            # 找到下一个 location 或 server 结束
            next_loc = content.find("location ", start + len(marker))
            next_server = content.find("server {", start + len(marker))
            end = min(next_loc, next_server) if next_loc > 0 and next_server > 0 else max(next_loc, next_server)
            if end < 0:
                end = len(content)
            block = content[start:end]
            for header in headers_to_hide:
                assert f"proxy_hide_header {header}" in block, (
                    f"location {location} 缺少 proxy_hide_header {header}"
                )
