import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendSessionValidationTest(unittest.TestCase):
    def read_web_file(self, relative_path: str) -> str:
        return (ROOT / "web" / "src" / relative_path).read_text(encoding="utf-8")

    def test_admin_store_validates_cookie_session_against_backend(self):
        source = self.read_web_file("stores/auth.js")

        self.assertIn("validateSession", source)
        self.assertIn("SESSION_VALIDATE_TIMEOUT_MS", source)
        self.assertIn("AbortController", source)
        self.assertIn("fetchWithTimeout('/api/auth/me'", source)
        self.assertIn("permissions", source)
        self.assertNotIn("if (!this.authed)", source)
        self.assertIn("sessionChecked: false", source)
        self.assertNotIn("sessionChecked: meta.sessionChecked === true", source)
        self.assertNotIn("sessionChecked: this.sessionChecked", source)

    def test_user_store_validates_cookie_session_against_backend(self):
        source = self.read_web_file("stores/userAuth.js")

        self.assertIn("validateSession", source)
        self.assertIn("SESSION_VALIDATE_TIMEOUT_MS", source)
        self.assertIn("AbortController", source)
        self.assertIn("fetchWithTimeout('/api/app/me'", source)
        self.assertNotIn("if (!this.authed)", source)
        self.assertIn("sessionChecked: false", source)
        self.assertNotIn("sessionChecked: meta.sessionChecked === true", source)
        self.assertNotIn("sessionChecked: this.sessionChecked", source)

    def test_router_does_not_block_public_login_routes_on_session_validation(self):
        source = self.read_web_file("router/index.js")

        admin_public = source.index("if (to.meta.public)")
        admin_private = source.index("if (!auth.sessionChecked && !(await auth.validateSession()))")
        user_public = source.index("if (isUserPublicRoute(to.path))")
        user_private = source.index("if (!userAuth.sessionChecked && !(await userAuth.validateSession()))")

        self.assertLess(admin_public, admin_private)
        self.assertLess(user_public, user_private)
        self.assertIn("validateAdminSessionInBackground(auth)", source)
        self.assertIn("validateUserSessionInBackground(userAuth)", source)
        self.assertNotIn("if (!auth.sessionChecked) {\n    await auth.validateSession()", source)
        self.assertNotIn("if (!userAuth.sessionChecked) {\n      await userAuth.validateSession()", source)

    def test_router_waits_for_session_validation_before_allowing_private_routes(self):
        source = self.read_web_file("router/index.js")

        self.assertIn("beforeEach(async", source)
        self.assertIn("await auth.validateSession()", source)
        self.assertIn("await userAuth.validateSession()", source)
        self.assertNotIn("auth.isAuthed && !auth.sessionChecked", source)
        self.assertNotIn("userAuth.isAuthed && !userAuth.sessionChecked", source)

    def test_router_uses_permission_points_for_admin_routes(self):
        source = self.read_web_file("router/index.js")

        self.assertIn("permissions: ['audit:read']", source)
        self.assertIn("permissions: ['users:read']", source)
        self.assertIn("auth.can(permission)", source)

    def test_root_route_defaults_to_user_login_when_not_authenticated(self):
        source = self.read_web_file("router/index.js")

        root_branch = source.index("if (isRootRoute(to.path))")
        admin_private = source.index("if (!auth.sessionChecked && !(await auth.validateSession()))")

        self.assertLess(root_branch, admin_private)
        self.assertIn("const isRootRoute = (path) => path === '/'", source)
        self.assertIn("path: '/u/login', query: { redirect: '/u' }", source)
        self.assertIn("return '/u'", source)

    def test_api_clients_attach_csrf_token_for_unsafe_cookie_requests(self):
        admin_http = self.read_web_file("api/http.js")
        user_http = self.read_web_file("api/userHttp.js")

        for source in (admin_http, user_http):
            self.assertIn("csrf_token", source)
            self.assertIn("X-CSRF-Token", source)
            self.assertIn("interceptors.request.use", source)

    def test_frontend_vite_proxy_target_is_configurable(self):
        source = (ROOT / "web" / "vite.config.js").read_text(encoding="utf-8")

        self.assertIn("loadEnv", source)
        self.assertIn("VITE_API_PROXY_TARGET", source)
        self.assertIn("const apiProxyTarget", source)
        self.assertIn("target: apiProxyTarget", source)
        self.assertIn("changeOrigin: true", source)
        self.assertIn("preview: {", source)

    def test_api_clients_surface_backend_unavailable_errors_clearly(self):
        admin_http = self.read_web_file("api/http.js")
        user_http = self.read_web_file("api/userHttp.js")
        error_helper = self.read_web_file("api/errorMessage.js")

        for source in (admin_http, user_http):
            self.assertIn("resolveApiErrorMessage", source)
        self.assertIn("后端服务不可用", error_helper)
        self.assertIn("ERR_NETWORK", error_helper)

    def test_user_settings_page_supports_push_notifications(self):
        source = self.read_web_file("views/user/UserSettings.vue")

        self.assertIn("pushNotifications", source)
        self.assertIn("Server酱", source)
        self.assertIn("QQ 邮箱 SMTP", source)
        self.assertIn("normalizePushNotifications", source)
        self.assertIn("pushNotifications", source)
        self.assertIn("/app/me", source)
        self.assertIn("pushNotifications", source)

    def test_user_settings_page_supports_clockin_location_search_and_coordinates(self):
        source = self.read_web_file("views/user/UserSettings.vue")

        for token in [
            "clockInLatitude",
            "clockInLongitude",
            "clockInProvince",
            "clockInCity",
            "clockInArea",
            "searchPlace",
            "/geocode/search",
        ]:
            self.assertIn(token, source)
        for token in [
            "reverseLookup",
            "geocodeReverseLoading",
            "geocodeReverseAbort",
            "坐标反查",
            "根据经纬度填充地址",
            "/app/geocode/search",
            "/app/geocode/reverse",
        ]:
            self.assertNotIn(token, source)
        self.assertIn("location.latitude", source)
        self.assertIn("location.longitude", source)
        self.assertIn("location.province", source)
        self.assertIn("location.city", source)
        self.assertIn("location.area", source)

    def test_admin_user_edit_uses_embeddable_openstreetmap(self):
        source = self.read_web_file("views/UserEdit.vue")

        self.assertIn("https://www.openstreetmap.org/export/embed.html", source)
        self.assertIn("mapDisplayUrl", source)
        self.assertIn("mapOpenUrl", source)
        self.assertIn("autoLocateSavedClockIn", source)
        self.assertIn("await autoLocateSavedClockIn()", source)
        self.assertIn("searchPlace({ silent: true })", source)
        self.assertIn("res.data?.latitude", source)
        self.assertIn("res.data?.longitude", source)
        self.assertIn("在新窗口打开地图", source)
        self.assertNotIn("https://www.mapchaxun.cn/jingweidu", source)


if __name__ == "__main__":
    unittest.main()
