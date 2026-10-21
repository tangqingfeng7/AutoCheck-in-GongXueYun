import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from server import api, verification_sessions as verification
from server.attendance_confirmation import verification_query_succeeded
from tests.test_authorization_lifecycle import DatabaseCase


class QueryResponseTest(unittest.TestCase):
    def test_business_success_supports_void_and_boolean(self):
        for response in ({'code': 200, 'data': None}, {'code': 200}, {'code': 200, 'data': True}):
            self.assertTrue(verification_query_succeeded(response))

    def test_explicit_false_error_and_unknown_shapes_not_confirmed(self):
        for response in ({'code': 200, 'data': False}, {'code': 500}, {}, None,
                         {'code': 200, 'data': 'true'}, {'code': 200, 'data': {}}, {'code': 200, 'data': 1}):
            self.assertFalse(verification_query_succeeded(response))

    def test_both_frontends_render_pending_as_information(self):
        root = Path(__file__).resolve().parents[1]
        for path in ('web/src/views/UserList.vue', 'web/src/views/user/UserHome.vue'):
            text = (root / path).read_text(encoding='utf-8')
            self.assertIn("if (result?.status === 'pending')", text)
            self.assertIn("notifyInfo(result.message || '考勤记录待服务端确认')", text)


class VerificationVoidResponseTest(DatabaseCase):
    def test_read_side_login_refresh_is_persisted(self):
        from sqlmodel import Session
        from server.models import User
        sid = self.session_id()
        client = Mock()
        client.query_alipay_clockin_verification.return_value = {'code': 200, 'data': None}
        client.get_checkin_records.return_value = []
        def factory(manager):
            manager.update_config({**manager.config['userInfo'], 'token': 'fixture-new-session'}, 'userInfo')
            return client
        with patch('server.coreApi.MainLogicApi.ApiClient', side_effect=factory), patch('server.attendance_confirmation.time.sleep'):
            verification.check_session(self.user, sid, db_engine=self.db)
        with Session(self.db) as session:
            self.assertEqual(session.get(User, 1).userInfo['token'], 'fixture-new-session')
        client.submit_clock_in.assert_not_called()

    def test_remote_expiration_invalidates_link_even_before_local_ttl(self):
        sid = self.session_id()
        client = Mock()
        client.query_alipay_clockin_verification.side_effect = ValueError('验证已过期，请重新签到再进行验证')
        client.get_checkin_records.return_value = []
        with patch('server.coreApi.MainLogicApi.ApiClient', return_value=client), patch('server.attendance_confirmation.time.sleep'):
            state = verification.check_session(self.user, sid, db_engine=self.db)
        self.assertEqual(state['state'], 'expired')
        self.assertEqual(state['check_state'], 'verification_expired')
        client.submit_clock_in.assert_not_called()

    def test_session_void_query_remains_pending_without_attendance(self):
        sid = self.session_id()
        client = Mock()
        client.query_alipay_clockin_verification.return_value = {'code': 200, 'data': None}
        client.get_checkin_records.return_value = []
        with patch('server.coreApi.MainLogicApi.ApiClient', return_value=client), patch('server.attendance_confirmation.time.sleep'):
            state = verification.check_session(self.user, sid, db_engine=self.db)
        self.assertEqual(state['state'], 'verified_pending_record')
        self.assertTrue(state['verification_confirmed'])
        self.assertFalse(state['record_confirmed'])
        client.submit_clock_in.assert_not_called()

    def test_dialog_void_query_never_claims_clockin_success_without_record(self):
        client = Mock()
        client.query_alipay_clockin_verification.return_value = {'code': 200, 'data': None}
        client.get_checkin_records.return_value = []
        with patch.object(api, 'ApiClient', return_value=client), patch.object(api, '_ensure_remote_runtime'), patch.object(api.time, 'sleep'):
            result, _ = api._continue_alipay_clockin_for_user(self.user, 'fixture-registration', 'START', attendance_date='2026-10-21')
        self.assertEqual(result['status'], 'pending')
        self.assertTrue(result['details']['verification_confirmed'])
        self.assertFalse(result['details']['record_confirmed'])
        client.submit_clock_in.assert_not_called()


if __name__ == '__main__':
    unittest.main()
