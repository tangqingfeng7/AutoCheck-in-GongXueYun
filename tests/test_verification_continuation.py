import datetime as dt
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import HTTPException, Response
from sqlmodel import Session
from server import api, verification_sessions as verification
from server.coreApi.MainLogicApi import ApiClient
from server.secret_store import decrypt_secret
from server.attendance_confirmation import OFFICIAL_ACCOUNT_VERIFICATION_NOTICE
from server.settings_store import get_setting, upsert_setting
from tests.test_alipay_clockin_verification import build_api_client, build_checkin_info
from tests.test_authorization_lifecycle import DatabaseCase


def captured_request():
    client = build_api_client()
    info = build_checkin_info()
    day = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
    info.update(createTime=day+' 08:30:00', attendenceTime=day+' 08:30:00')
    response = {'code': 200, 'msg': '304', 'data': json.dumps({'attendanceId': 'fixture-attendance-id'})}
    with patch.object(client, '_post_request', return_value=response):
        client.submit_clock_in(info)
    return client, getattr(client, '_pending_submission', None), day


class CapturedSubmissionTest(unittest.TestCase):
    def test_known_official_notice_can_continue_without_inventing_attendance_id(self):
        client,context,day=captured_request()
        context.update(attendanceId=None,response_data=OFFICIAL_ACCOUNT_VERIFICATION_NOTICE)
        with patch.object(client,'_post_request',return_value={'code':200,'msg':'success'}) as post:
            self.assertEqual(client.resume_clock_in_submission(context,'fixture-registration',day,'START'),'responded')
        post.assert_called_once()
        body=post.call_args.args[2]
        self.assertIsNone(body['attendanceId'])
        self.assertEqual(body['appUuid'],context['body']['appUuid'])
        self.assertEqual(body['outRegisterNo'],'fixture-registration')

    def test_unknown_plaintext_is_not_treated_as_supported_notice(self):
        client,context,day=captured_request()
        context.update(attendanceId=None,response_data='Some other server message')
        with patch.object(client,'_post_request') as post,self.assertRaises(ValueError):
            client.resume_clock_in_submission(context,'fixture-registration',day,'START')
        post.assert_not_called()
    def test_json_object_string_is_parsed_and_original_identity_reused(self):
        client, context, day = captured_request()
        self.assertEqual(context['attendanceId'], 'fixture-attendance-id')
        original = json.loads(json.dumps(context))
        with patch.object(client, '_post_request', return_value={'code':200, 'msg':'success'}) as post:
            self.assertEqual(client.resume_clock_in_submission(context, 'fixture-registration', day, 'START'), 'responded')
        post.assert_called_once()
        path, headers, payload = post.call_args.args
        self.assertEqual(path, original['path'])
        for key in ('appUuid', 'createTime', 'attendenceTime', 'device', 'address', 'latitude', 'longitude', 'planId', 'userId', 'attachments'):
            self.assertEqual(payload[key], original['body'][key])
        self.assertEqual(payload['attendanceId'], 'fixture-attendance-id')
        self.assertEqual(payload['outRegisterNo'], 'fixture-registration')
        self.assertEqual(context, original)

    def test_opaque_response_is_not_guessed_as_attendance_id(self):
        client=build_api_client()
        with patch.object(client, '_post_request', return_value={'code':200,'msg':'304','data':'opaque-fixture-private'}):
            result=client.submit_clock_in(build_checkin_info())
        self.assertNotIn('attendanceId',result)
        self.assertIsNone(client._pending_submission['attendanceId'])
        self.assertEqual(client._pending_submission['response_data'],'opaque-fixture-private')

    def test_binding_mismatch_never_writes(self):
        for field, value in (('userId','other'),('planId','other'),('device','other'),('type','END'),('createTime','2000-01-01 08:30:00')):
            client, context, day=captured_request();context['body'][field]=value
            with patch.object(client,'_post_request') as post, self.assertRaises(ValueError):
                client.resume_clock_in_submission(context,'fixture-registration',day,'START')
            post.assert_not_called()

    def test_missing_id_and_arbitrary_path_never_write(self):
        for field,value in (('attendanceId',None),('path','https://other.invalid/save'),('version',9)):
            client,context,day=captured_request();context[field]=value
            with patch.object(client,'_post_request') as post, self.assertRaises(ValueError):
                client.resume_clock_in_submission(context,'fixture-registration',day,'START')
            post.assert_not_called()

    def test_new_challenge_stops_after_one_write_without_captcha_loop(self):
        client,context,day=captured_request()
        for msg in ('302','303','304'):
            with patch.object(client,'_post_request',return_value={'code':200,'msg':msg}) as post, patch.object(client,'solve_click_word_captcha') as solve:
                self.assertEqual(client.resume_clock_in_submission(context,'fixture-registration',day,'START'),'verification_required_again')
            post.assert_called_once();solve.assert_not_called()


class ResumeSessionTest(DatabaseCase):
    def test_known_notice_session_can_continue_once_without_id(self):
        _,context,day=captured_request()
        context.update(attendanceId=None,response_data=OFFICIAL_ACCOUNT_VERIFICATION_NOTICE)
        sid=verification.create_session(1,'default',day,'START',{
            'verification_type':'account','registerUrl':'alipays://platformapi/startapp?appId=fixture',
            'outRegisterNo':'fixture-registration'},db_engine=self.db,submission_context=context)
        with Session(self.db) as s:
            self.assertTrue(verification.list_sessions(s,self.user)[0]['resume_available'])
        client=self.client();state=self.run_resume(sid,client)
        self.assertTrue(state['resume_attempted']);self.assertFalse(state['record_confirmed'])
        self.run_resume(sid,client)
        client.resume_clock_in_submission.assert_called_once()

    def test_existing_captured_notice_flag_is_upgraded_by_read_only_check(self):
        _,context,day=captured_request()
        context.update(attendanceId=None,response_data=OFFICIAL_ACCOUNT_VERIFICATION_NOTICE)
        sid=verification.create_session(1,'default',day,'START',{
            'verification_type':'account','registerUrl':'alipays://platformapi/startapp?appId=fixture',
            'outRegisterNo':'fixture-registration'},db_engine=self.db,submission_context=context)
        with Session(self.db) as s:
            row=get_setting(s,verification.PREFIX+sid);value=dict(row.value)
            value.update(has_submission_context=False,resume_state='response_context_missing')
            upsert_setting(s,verification.PREFIX+sid,value);s.commit()
        client=self.client()
        with patch('server.coreApi.MainLogicApi.ApiClient',return_value=client),patch('server.attendance_confirmation.time.sleep'):
            result=verification.check_session(self.user,sid,db_engine=self.db)
        self.assertTrue(result['resume_available']);self.assertEqual(result['resume_state'],'ready')
        client.resume_clock_in_submission.assert_not_called()
    def captured_session(self):
        _, context, day = captured_request()
        sid=verification.create_session(1,'default',day,'START',{
            'verification_type':'account','registerUrl':'alipays://platformapi/startapp?appId=fixture',
            'outRegisterNo':'fixture-registration'},db_engine=self.db,submission_context=context)
        return sid,day

    def client(self):
        client=Mock()
        client.get_checkin_records.return_value=[]
        client.query_alipay_clockin_verification.return_value={'code':200,'data':None}
        client.resume_clock_in_submission.return_value='responded'
        return client

    def run_resume(self,sid,client):
        with patch('server.coreApi.MainLogicApi.ApiClient',return_value=client), patch('server.attendance_confirmation.time.sleep'):
            return verification.resume_session(self.user,sid,db_engine=self.db)

    def test_original_context_encrypted_and_not_public(self):
        sid,_=self.captured_session()
        with Session(self.db) as s:
            row=get_setting(s,verification.PREFIX+sid)
            self.assertNotIn('fixture-attendance-id',json.dumps(row.value))
            self.assertIn('fixture-attendance-id',decrypt_secret(row.value['payload']))
            public=verification.list_sessions(s,self.user)
            self.assertNotIn('"submission_context"',json.dumps(public));self.assertTrue(public[0]['resume_available'])

    def test_durable_claim_exists_before_write_and_duplicate_is_not_replayed(self):
        sid,_=self.captured_session();client=self.client()
        def submit(*args):
            with Session(self.db) as s:
                data=get_setting(s,verification.PREFIX+sid).value
                self.assertTrue(data['resume_attempted']);self.assertEqual(data['resume_state'],'uncertain')
            return 'responded'
        client.resume_clock_in_submission.side_effect=submit
        state=self.run_resume(sid,client)
        self.assertFalse(state['record_confirmed']);self.assertFalse(state['resume_available'])
        self.assertEqual(state['resume_state'],'responded')
        self.run_resume(sid,client)
        client.resume_clock_in_submission.assert_called_once()

    def test_timeout_never_replays_even_after_restart(self):
        sid,_=self.captured_session();client=self.client()
        client.resume_clock_in_submission.side_effect=TimeoutError('private-fixture-response')
        state=self.run_resume(sid,client)
        self.assertEqual(state['resume_state'],'uncertain');self.assertFalse(state['record_confirmed'])
        self.assertNotIn('private-fixture',json.dumps(state))
        self.run_resume(sid,self.client())
        client.resume_clock_in_submission.assert_called_once()

    def test_already_confirmed_record_does_not_submit(self):
        sid,day=self.captured_session();client=self.client()
        client.get_checkin_records.return_value=[{'type':'START','createTime':day+' 08:30:00'}]
        state=self.run_resume(sid,client)
        self.assertTrue(state['record_confirmed'])
        client.resume_clock_in_submission.assert_not_called();client.query_alipay_clockin_verification.assert_not_called()

    def test_success_requires_matching_type_and_date(self):
        sid,day=self.captured_session();client=self.client()
        client.get_checkin_records.side_effect=[[],[{'type':'START','createTime':day+' 08:30:00'}]]
        state=self.run_resume(sid,client)
        self.assertTrue(state['record_confirmed']);self.assertEqual(state['state'],'record_confirmed')
        with Session(self.db) as s:self.assertEqual(get_setting(s,verification.PREFIX+sid).value['payload'],'')
        client.resume_clock_in_submission.assert_called_once()

    def test_false_authorization_or_record_query_failure_does_not_submit(self):
        for cause in ('authorization','records'):
            sid,_=self.captured_session();client=self.client()
            if cause=='authorization':client.query_alipay_clockin_verification.return_value={'code':200,'data':False}
            else:client.get_checkin_records.side_effect=TimeoutError()
            with self.assertRaises(HTTPException):self.run_resume(sid,client)
            client.resume_clock_in_submission.assert_not_called()
            with Session(self.db) as s:self.assertFalse(get_setting(s,verification.PREFIX+sid).value['resume_attempted'])

    def test_legacy_or_expired_session_rejected_without_write(self):
        sid=self.session_id();client=self.client()
        with self.assertRaises(HTTPException):self.run_resume(sid,client)
        client.resume_clock_in_submission.assert_not_called()
        sid,_=self.captured_session()
        with Session(self.db) as s:
            row=get_setting(s,verification.PREFIX+sid);value=dict(row.value);value['expires_at']=0
            upsert_setting(s,verification.PREFIX+sid,value);s.commit()
        with self.assertRaises(HTTPException):self.run_resume(sid,client)
        client.resume_clock_in_submission.assert_not_called()

    def test_other_account_cannot_resume_or_create_lock(self):
        from server.models import User
        sid,_=self.captured_session()
        for other in (User(id=2,tenant_id='default',phone='other',password='fixture'),User(id=1,tenant_id='other',phone='other',password='fixture')):
            with patch.object(verification,'acquire_task_lock') as lock, self.assertRaises(HTTPException) as err:
                verification.resume_session(other,sid,db_engine=self.db)
            self.assertEqual(err.exception.status_code,404);lock.assert_not_called()

    def test_inflight_transaction_does_not_start_another_write(self):
        from server.execution_locks import acquire_task_lock,release_task_lock
        sid,_=self.captured_session();client=self.client()
        token=acquire_task_lock('verification-check:default:'+sid,db_engine=self.db)
        try:
            with self.assertRaises(HTTPException):self.run_resume(sid,client)
        finally:release_task_lock(token,db_engine=self.db)
        client.resume_clock_in_submission.assert_not_called()

    def test_check_endpoint_remains_read_only_with_original_context(self):
        sid,_=self.captured_session();client=self.client()
        with patch('server.coreApi.MainLogicApi.ApiClient',return_value=client),patch('server.attendance_confirmation.time.sleep'):
            state=verification.check_session(self.user,sid,db_engine=self.db)
        self.assertFalse(state['record_confirmed']);client.resume_clock_in_submission.assert_not_called()

    def test_process_interruption_keeps_claim_and_prevents_a_new_write(self):
        sid,_=self.captured_session();client=self.client()
        client.resume_clock_in_submission.side_effect=SystemExit('fixture process interruption')
        with self.assertRaises(SystemExit):self.run_resume(sid,client)
        restarted=self.client()
        result=self.run_resume(sid,restarted)
        self.assertEqual(result['resume_state'],'uncertain')
        restarted.resume_clock_in_submission.assert_not_called()

    def test_wrong_date_or_type_is_not_success_after_response(self):
        sid,day=self.captured_session();client=self.client()
        client.get_checkin_records.return_value=[{'type':'END','createTime':day+' 08:30:00'},
                                                {'type':'START','createTime':'2000-01-01 08:30:00'}]
        state=self.run_resume(sid,client)
        self.assertFalse(state['record_confirmed']);self.assertEqual(state['resume_state'],'responded')

    def test_task_passes_private_context_only_to_encrypted_session(self):
        from server import task_runner
        from server.clockin_preauthorization import ClockInPreauthorizationHooks
        from tests.test_alipay_clockin_verification import build_task_api_client,build_task_config
        _,context,day=captured_request()
        client=build_task_api_client({'status':'verification_required'})
        client._pending_submission=context
        hooks=ClockInPreauthorizationHooks(tenant_id='default',user_id=1,db_engine=self.db)
        with patch.object(task_runner,'upload_img',return_value=[]):
            result=task_runner.perform_clock_in(client,build_task_config(),forced_checkin_type='START',
                target_time=dt.datetime.fromisoformat(day+'T08:30:00'),preauthorization_hooks=hooks)
        self.assertNotIn('submission_context',json.dumps(result))
        with Session(self.db) as s:
            stored=get_setting(s,verification.PREFIX+result['details']['verification_session_id']).value
            self.assertEqual(json.loads(decrypt_secret(stored['payload']))['submission_context'],context)

    def test_explicit_resume_routes_and_frontend_warning(self):
        from server.main import app
        paths={r.path for r in app.routes}
        self.assertIn('/api/users/{user_id}/verification-sessions/{session_id}/resume',paths)
        self.assertIn('/api/app/verification-sessions/{session_id}/resume',paths)
        with Session(self.db) as s, patch.object(verification,'resume_session',return_value={'state':'verified_pending_record'}) as resume, patch.object(api,'_rate_limit'):
            response=Response()
            result=api.resume_admin_verification_session(1,'f'*32,response,session=s,operator={'tenant_id':'default','role':'admin'})
        self.assertEqual(response.headers['cache-control'],'no-store');resume.assert_called_once()
        root=Path(__file__).resolve().parents[1]
        frontend=(root/'web/src/components/TaskStatusPanel.vue').read_text(encoding='utf-8')
        self.assertIn('/resume`',frontend);self.assertIn('授权完成，续提一次',frontend)


if __name__=='__main__':unittest.main()
