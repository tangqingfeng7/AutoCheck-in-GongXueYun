import json
import os
import unittest
from unittest.mock import Mock, patch

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from server import verification_sessions as verification
from server.models import User
from server.settings_store import get_setting, upsert_setting


class VerificationRecheckTest(unittest.TestCase):
    def setUp(self):
        self.db = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(self.db)
        self.key = patch.dict(os.environ, {'USER_PASSWORD_KEY': 'recheck-fixture-key'})
        self.key.start()
        with Session(self.db) as session:
            self.user = User(id=1, tenant_id='default', phone='fixture', password='fixture',
                             userInfo={'token': 'fixture'}, last_status='Pending')
            session.add(self.user)
            session.commit()
            session.refresh(self.user)
            session.expunge(self.user)
        self.sid = verification.create_session(1, 'default', '2026-10-21', 'END', {
            'verification_type': 'account', 'outRegisterNo': 'fixture-registration',
            'registerUrl': 'alipays://platformapi/startapp?appId=fixture'}, db_engine=self.db)
        self.client = Mock()
        self.client.get_checkin_records.return_value = []

    def tearDown(self):
        self.key.stop()
        self.db.dispose()

    def check(self):
        with patch('server.coreApi.MainLogicApi.ApiClient', return_value=self.client), \
                patch('server.attendance_confirmation.time.sleep'):
            return verification.check_session(self.user, self.sid, db_engine=self.db)

    def allow_next_check(self):
        with Session(self.db) as session:
            row = get_setting(session, verification.PREFIX + self.sid, 'default')
            upsert_setting(session, verification.PREFIX + self.sid,
                           {**row.value, 'last_checked': 0}, 'default')
            session.commit()

    def test_void_success_before_authorization_does_not_disable_later_query(self):
        def query(_registration):
            if self.client.query_alipay_clockin_verification.call_count == 2:
                self.client.get_checkin_records.return_value = [
                    {'type': 'END', 'createTime': '2026-10-21 18:10:00'}]
            return {'code': 200, 'data': None}

        self.client.query_alipay_clockin_verification.side_effect = query
        first = self.check()
        self.assertEqual(first['state'], 'verified_pending_record')
        self.allow_next_check()
        second = self.check()
        print(json.dumps({'scenario': 'authorization_after_early_void_query',
                          'query_calls': self.client.query_alipay_clockin_verification.call_count,
                          'first_state': first['state'], 'final_state': second['state'],
                          'record_confirmed': second['record_confirmed'],
                          'save_calls': self.client.submit_clock_in.call_count}, sort_keys=True))
        self.assertEqual(second['state'], 'record_confirmed')
        self.assertEqual(self.client.query_alipay_clockin_verification.call_count, 2)
        self.client.submit_clock_in.assert_not_called()
        self.client.submit_clock_in_replace.assert_not_called()
        self.check()
        self.assertEqual(self.client.query_alipay_clockin_verification.call_count, 2)

    def test_expiration_after_void_success_is_not_hidden_by_cached_flag(self):
        self.client.query_alipay_clockin_verification.side_effect = [
            {'code': 200, 'data': None}, ValueError('验证已过期，请重新签到再进行验证')]
        self.check()
        self.allow_next_check()
        result = self.check()
        self.assertEqual(result['state'], 'expired')
        self.assertEqual(result['check_state'], 'verification_expired')
        self.client.submit_clock_in.assert_not_called()

    def test_throttle_still_blocks_immediate_double_click(self):
        self.client.query_alipay_clockin_verification.return_value = {'code': 200, 'data': None}
        self.check()
        self.check()
        self.client.query_alipay_clockin_verification.assert_called_once()
        self.client.submit_clock_in.assert_not_called()


if __name__ == '__main__':
    unittest.main()
