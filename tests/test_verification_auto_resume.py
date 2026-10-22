import time
import unittest
from unittest.mock import Mock, patch
from sqlmodel import Session
from server import verification_sessions as verification
from server.models import User, Tenant
from server.settings_store import get_setting, upsert_setting
from tests.test_authorization_lifecycle import DatabaseCase
from tests.test_verification_continuation import captured_request


class AutomaticContinuationTest(DatabaseCase):
    def captured_session(self):
        _, context, self.day = captured_request()
        return verification.create_session(1, 'default', self.day, 'START', {
            'verification_type': 'account', 'registerUrl': 'alipays://platformapi/startapp?appId=fixture',
            'outRegisterNo': 'fixture-registration'}, db_engine=self.db, submission_context=context)

    def client(self):
        client = Mock()
        client.get_checkin_records.return_value = []
        client.query_alipay_clockin_verification.return_value = {'code': 200, 'data': None}
        client.resume_clock_in_submission.return_value = 'responded'
        return client

    def scan(self, client):
        with patch('server.coreApi.MainLogicApi.ApiClient', return_value=client), patch('server.attendance_confirmation.time.sleep'):
            verification.process_pending_sessions(db_engine=self.db)

    def state(self, sid):
        with Session(self.db) as s:
            return verification.public(get_setting(s, verification.PREFIX + sid).value)

    def test_background_continues_without_page_or_manual_clockin_schedule(self):
        sid = self.captured_session(); client = self.client()
        with Session(self.db) as s:
            user = s.get(User, 1); user.enable_clockin = False; s.add(user); s.commit()
        def records(*args):
            return [{'type': 'START', 'createTime': self.day+' 08:30:00'}] if client.resume_clock_in_submission.call_count else []
        client.get_checkin_records.side_effect = records
        self.scan(client); self.force_check(sid); self.scan(client)
        self.assertTrue(self.state(sid)['record_confirmed'])
        client.resume_clock_in_submission.assert_called_once()

    def test_early_check_false_then_authorization_success(self):
        sid = self.captured_session(); client = self.client()
        client.query_alipay_clockin_verification.return_value = {'code': 200, 'data': False}
        self.scan(client)
        self.assertEqual(self.state(sid)['state'], 'awaiting_verification')
        client.resume_clock_in_submission.assert_not_called()
        self.force_check(sid)
        client.query_alipay_clockin_verification.return_value = {'code': 200, 'data': None}
        self.scan(client)
        self.assertTrue(self.state(sid)['resume_attempted'])
        client.resume_clock_in_submission.assert_called_once()

    def test_timeout_and_restarted_scanner_never_replay(self):
        sid = self.captured_session(); client = self.client()
        client.resume_clock_in_submission.side_effect = TimeoutError('private-fixture')
        self.scan(client)
        self.assertEqual(self.state(sid)['resume_state'], 'uncertain')
        self.force_check(sid); restarted = self.client(); self.scan(restarted)
        client.resume_clock_in_submission.assert_called_once()
        restarted.resume_clock_in_submission.assert_not_called()

    def test_continuous_three_second_polling_and_terminal_stop(self):
        sid = self.captured_session(); client = self.client(); now = time.time()
        client.query_alipay_clockin_verification.return_value = {'code': 200, 'data': False}
        for offset, expected_queries in ((0, 1), (1, 1), (3, 2), (6, 3)):
            with patch('server.verification_sessions.time.time', return_value=now + offset):
                self.scan(client)
            self.assertEqual(client.query_alipay_clockin_verification.call_count, expected_queries)
        self.assertFalse(self.state(sid)['resume_attempted'])
        client.query_alipay_clockin_verification.return_value = {'code': 200, 'data': True}
        def records(*args):
            return [{'type': 'START', 'createTime': self.day+' 08:30:00'}] if client.resume_clock_in_submission.call_count else []
        client.get_checkin_records.side_effect = records
        with patch('server.verification_sessions.time.time', return_value=now + 9):
            self.scan(client)
        queries = client.query_alipay_clockin_verification.call_count
        with patch('server.verification_sessions.time.time', return_value=now + 12):
            self.scan(client)
        self.assertEqual(client.query_alipay_clockin_verification.call_count, queries)
        self.assertTrue(self.state(sid)['record_confirmed'])
        client.resume_clock_in_submission.assert_called_once()

    def test_direct_check_uses_same_three_second_throttle(self):
        sid = self.captured_session(); client = self.client(); now = time.time()
        with patch('server.coreApi.MainLogicApi.ApiClient', return_value=client), patch('server.attendance_confirmation.time.sleep'):
            for offset, expected_queries in ((0, 1), (1, 1), (3, 2)):
                with patch('server.verification_sessions.time.time', return_value=now + offset):
                    verification.check_session(self.user, sid, db_engine=self.db)
                self.assertEqual(client.query_alipay_clockin_verification.call_count, expected_queries)
        client.resume_clock_in_submission.assert_not_called()

    def test_already_recorded_does_not_continue(self):
        sid = self.captured_session(); client = self.client()
        client.get_checkin_records.return_value = [{'type': 'START', 'createTime': self.day+' 08:30:00'}]
        self.scan(client)
        self.assertTrue(self.state(sid)['record_confirmed'])
        client.resume_clock_in_submission.assert_not_called()

    def test_failed_record_query_or_verification_never_continues(self):
        for cause in ('records', 'verification'):
            with self.subTest(cause=cause):
                sid = self.captured_session(); client = self.client()
                if cause == 'records': client.get_checkin_records.side_effect = TimeoutError()
                else: client.query_alipay_clockin_verification.side_effect = TimeoutError()
                self.scan(client)
                self.assertFalse(self.state(sid)['resume_attempted'])
                client.resume_clock_in_submission.assert_not_called()

    def test_authorization_must_still_be_valid_at_write_time(self):
        sid = self.captured_session(); client = self.client()
        client.query_alipay_clockin_verification.side_effect = [{'code': 200, 'data': True}, {'code': 200, 'data': False}]
        self.scan(client)
        self.assertFalse(self.state(sid)['resume_attempted'])
        client.resume_clock_in_submission.assert_not_called()

    def test_missing_context_and_face_transactions_only_check(self):
        for kind in ('account', 'face'):
            sid = self.session_id(kind); client = self.client(); self.scan(client)
            client.resume_clock_in_submission.assert_not_called()
            self.assertFalse(self.state(sid)['resume_attempted'])

    def test_expired_and_inactive_tenant_do_not_even_query(self):
        sid = self.captured_session(); client = self.client()
        with Session(self.db) as s:
            row = get_setting(s, verification.PREFIX + sid); value = dict(row.value); value['expires_at'] = 0
            upsert_setting(s, verification.PREFIX + sid, value); s.commit()
        self.scan(client); client.query_alipay_clockin_verification.assert_not_called()
        self.captured_session()
        with Session(self.db) as s:
            s.add(Tenant(id='default', name='Fixture', status='disabled')); s.commit()
        self.scan(client); client.query_alipay_clockin_verification.assert_not_called()

    def test_one_failed_session_does_not_stop_following_sessions(self):
        first = self.captured_session(); second = self.captured_session(); client = self.client()
        with patch.object(verification, 'check_session', side_effect=[RuntimeError('fixture'), {
            'verification_confirmed': True, 'resume_available': True, 'check_state': 'checked'}]), patch.object(verification, 'resume_session') as resume:
            self.scan(client)
        resume.assert_called_once()
        self.assertIn(resume.call_args.args[1], (first, second))

    def test_scheduler_registers_three_second_background_scan(self):
        from server import scheduler as module
        scheduler = Mock(); scheduler.running = False
        with patch.object(module, 'scheduler', scheduler), patch.object(module, '_iter_schedulable_users', return_value=[]), patch.object(module, 'engine', self.db):
            module.start_scheduler()
        job = next(c for c in scheduler.add_job.call_args_list if c.kwargs.get('id') == 'verification_sessions')
        self.assertIs(job.args[0], verification.process_pending_sessions)
        self.assertEqual(job.kwargs['seconds'], 3)
        self.assertEqual(job.kwargs['max_instances'], 1)


if __name__ == '__main__': unittest.main()
