import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendTenantLoginTest(unittest.TestCase):
    def read_web_file(self, relative_path: str) -> str:
        return (ROOT / "web" / "src" / relative_path).read_text(encoding="utf-8")

    def test_admin_login_does_not_expose_or_submit_tenant_id(self):
        source = self.read_web_file("views/Login.vue")

        self.assertNotIn("tenant_id", source)
        self.assertNotIn("tenantId", source)
        self.assertNotIn('v-model="form.tenant_id"', source)
        self.assertNotIn("tenant_id: form.tenant_id", source)

    def test_admin_login_does_not_submit_mfa_code(self):
        source = self.read_web_file("views/Login.vue")

        self.assertNotIn("mfa_code", source)
        self.assertNotIn("one-time-code", source)
        self.assertNotIn("MFA", source)

    def test_admin_security_page_and_mfa_route_are_removed(self):
        router_source = self.read_web_file("router/index.js")
        app_source = self.read_web_file("App.vue")

        self.assertNotIn("SecuritySettings.vue", router_source)
        self.assertNotIn("/security", router_source)
        self.assertFalse((ROOT / "web" / "src" / "views" / "SecuritySettings.vue").exists())
        self.assertNotIn("账号安全", app_source)

    def test_user_login_and_register_do_not_expose_or_submit_tenant_id(self):
        login_source = self.read_web_file("views/user/UserLogin.vue")
        register_source = self.read_web_file("views/user/UserRegister.vue")

        for source in (login_source, register_source):
            self.assertNotIn("tenant_id", source)
            self.assertNotIn("tenantId", source)
            self.assertNotIn('v-model="form.tenant_id"', source)
            self.assertNotIn("tenant_id: form.tenant_id", source)

    def test_tenant_metadata_is_not_persisted_in_frontend_auth_state(self):
        admin_store = self.read_web_file("stores/auth.js")
        user_store = self.read_web_file("stores/userAuth.js")

        self.assertNotIn("tenantId", admin_store)
        self.assertNotIn("tenantId", user_store)
        self.assertNotIn("token:", admin_store)
        self.assertNotIn("token:", user_store)

    def test_tenant_management_frontend_surface_is_removed(self):
        router_source = self.read_web_file("router/index.js")
        app_source = self.read_web_file("App.vue")

        self.assertNotIn("TenantManagement.vue", router_source)
        self.assertNotIn("/tenants", router_source)
        self.assertNotIn("tenants:read", router_source)
        self.assertNotIn("tenants:read", app_source)
        self.assertFalse((ROOT / "web" / "src" / "views" / "TenantManagement.vue").exists())

    def test_user_register_password_rule_matches_backend_minimum(self):
        source = self.read_web_file("views/user/UserRegister.vue")

        self.assertIn("form.password.length < 10", source)
        self.assertNotIn("form.password.length < 6", source)
        self.assertIn("密码至少 10 位", source)

    def test_frontend_quality_gate_rejects_mfa_reintroduction_in_any_source_file(self):
        probe = ROOT / "web" / "src" / "__mfa_quality_gate_probe__.js"
        probe.write_text("export const removedEndpoint = '/auth/mfa/status'\n", encoding="utf-8")
        try:
            result = subprocess.run(
                ["node", "scripts/frontend_quality_gate.mjs"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            probe.unlink(missing_ok=True)

        output = (result.stdout or "") + (result.stderr or "")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("removed MFA", output)


if __name__ == "__main__":
    unittest.main()
