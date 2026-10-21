import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from server import api, verification_sessions as verification
from server.database import get_session
from server.auth import get_user
from server.models import User
from server.settings_store import get_setting, upsert_setting
from tests.test_authorization_lifecycle import DatabaseCase


class ClearVerificationSessionsTest(DatabaseCase):
    def test_clear_all_not_only_twenty_and_preserve_other_accounts_and_data(self):
        for _ in range(25):
            self.session_id()
        with Session(self.db) as s:
            upsert_setting(s, verification.PREFIX + 'a' * 32, {'user_id': 2})
            upsert_setting(s, verification.PREFIX + 'b' * 32, {'user_id': 1}, 'other')
            upsert_setting(s, 'attendance-monitor:1', {'record_confirmed': True})
            s.commit()
            self.assertEqual(len(verification.list_sessions(s, self.user)), 20)
            self.assertEqual(verification.clear_sessions(s, self.user), {'cleared': 25})
        with Session(self.db) as s:
            self.assertEqual(verification.list_sessions(s, self.user), [])
            self.assertIsNotNone(get_setting(s, verification.PREFIX + 'a' * 32))
            self.assertIsNotNone(get_setting(s, verification.PREFIX + 'b' * 32, 'other'))
            self.assertTrue(get_setting(s, 'attendance-monitor:1').value['record_confirmed'])
            self.assertEqual(s.get(User, 1).last_execution_result, self.user.last_execution_result)
            self.assertEqual(verification.clear_sessions(s, self.user), {'cleared': 0})

    def test_only_matching_pending_reminders_are_cancelled(self):
        sid = self.session_id()
        with Session(self.db) as s:
            for name, state, session_id in [('own', 'retry', sid), ('sent', 'sent', sid), ('other', 'queued', 'other')]:
                upsert_setting(s, 'mail-outbox:' + name, {'status': state, 'verification_session_id': session_id, 'payload': 'fixture'})
            s.commit()
            verification.clear_sessions(s, self.user)
        with Session(self.db) as s:
            self.assertEqual(get_setting(s, 'mail-outbox:own').value['status'], 'cancelled')
            self.assertEqual(get_setting(s, 'mail-outbox:own').value['payload'], '')
            self.assertEqual(get_setting(s, 'mail-outbox:sent').value['status'], 'sent')
            self.assertEqual(get_setting(s, 'mail-outbox:other').value['status'], 'queued')

    def test_non_default_tenant_clear_does_not_touch_default(self):
        sid = self.session_id()
        other = User(id=1, tenant_id='other', phone='fixture', password='fixture')
        with Session(self.db) as s:
            upsert_setting(s, verification.PREFIX + sid, {'id': sid, 'user_id': 1}, 'other')
            s.commit()
            self.assertEqual(verification.clear_sessions(s, other), {'cleared': 1})
            self.assertIsNotNone(get_setting(s, verification.PREFIX + sid))

    def test_http_routes_are_scoped_and_require_auth(self):
        sid = self.session_id()
        def db():
            with Session(self.db) as s:
                yield s
        app = FastAPI()
        app.include_router(api.router)
        app.dependency_overrides[get_session] = db
        with TestClient(app) as client:
            self.assertIn(client.delete('/app/verification-sessions').status_code, (401, 403))
            self.assertIn(client.delete('/users/1/verification-sessions').status_code, (401, 403))
        app.dependency_overrides[api.require_tasks_run] = lambda: {'role': 'admin', 'tenant_id': 'default'}
        with TestClient(app) as client:
            self.assertEqual(client.delete('/users/999/verification-sessions').status_code, 404)
            response = client.delete('/users/1/verification-sessions')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {'cleared': 1})
            self.assertEqual(response.headers['cache-control'], 'no-store')
        self.session_id()
        app.dependency_overrides[get_user] = lambda: {'role': 'user'}
        with patch.object(api, '_get_authed_app_user', return_value=object()), \
             patch.object(api, '_get_bound_task_user', return_value=self.user), TestClient(app) as client:
            self.assertEqual(client.delete('/app/verification-sessions').json(), {'cleared': 1})
        with Session(self.db) as s:
            self.assertIsNone(get_setting(s, verification.PREFIX + sid))


if __name__ == '__main__':
    unittest.main()
