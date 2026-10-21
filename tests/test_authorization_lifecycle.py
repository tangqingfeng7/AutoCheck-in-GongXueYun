import datetime as dt
import json
import os
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException, Response
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from server import api, task_status, task_runner, verification_sessions as verification
from server.models import User
from server.settings_store import get_setting, upsert_setting
from server.secret_store import encrypt_secret, decrypt_secret
from server.attendance_reconciliation import reconcile_results


class DatabaseCase(unittest.TestCase):
    def setUp(self):
        self.db = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(self.db)
        self.patches = [patch.dict(os.environ, {'USER_PASSWORD_KEY':'fixture-encryption-key', 'SCHEDULER_JITTER_SECONDS':'0'}),
                        patch.object(verification, 'engine', self.db), patch.object(task_status, 'engine', self.db)]
        for p in self.patches: p.start()
        with Session(self.db) as s:
            self.user = User(id=1, tenant_id='default', phone='fixture', password='fixture',
                clockIn={'mode':'none','schedule':{'startTime':'08:30','endTime':'17:30','weekdays':[1,2,3,4,5]}},
                userInfo={'token':'fixture'}, last_status='Pending', last_run_time='2026-10-21 08:30:00',
                last_execution_result=[{'task_type':'打卡','status':'pending','message':'结果待确认',
                    'details':{'attendance_date':'2026-10-21','target_type':'START','record_confirmed':False}}])
            s.add(self.user); s.commit(); s.refresh(self.user); s.expunge(self.user)

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.db.dispose()

    def session_id(self, verification_type='account'):
        return verification.create_session(1, 'default', '2026-10-21', 'START', {
            'verification_type':verification_type, 'registerUrl':'alipays://platformapi/startapp?appId=fixture-private-link',
            'outRegisterNo':'fixture-private-registration'}, db_engine=self.db)

    def force_check(self, sid):
        with Session(self.db) as s:
            row=get_setting(s,verification.PREFIX+sid,'default');value=dict(row.value);value['last_checked']=0
            upsert_setting(s,verification.PREFIX+sid,value,'default');s.commit()


class SecretSettingsTest(DatabaseCase):
    def store(self):
        with Session(self.db) as s:
            api._save_notification_settings(s,{'username':'sender@qq.com','password':'fixture-auth-code','enabled':True,'from':'Fixture'})
            s.commit()

    def test_get_and_patch_response_never_expose_authorization_code(self):
        self.store()
        with Session(self.db) as s:
            data=api._sanitize_notification_settings_for_read(api._get_notification_settings(s))
            self.assertTrue(data['smtp']['hasPassword']);self.assertNotIn('password',data['smtp'])
            updated=api._save_notification_settings(s,{'username':'sender@qq.com','password':'','from':'Updated'})
            s.commit()
            self.assertEqual(updated['smtp']['password'],'fixture-auth-code')
            response=api._sanitize_notification_settings_for_read(updated)
            self.assertNotIn('fixture-auth-code',json.dumps(response))
            stored=get_setting(s,'notifications').value['smtp']['password']
            self.assertTrue(stored.startswith('enc$'));self.assertEqual(decrypt_secret(stored),'fixture-auth-code')

    def test_blank_test_payload_uses_saved_secret_without_sending_real_mail(self):
        self.store()
        with Session(self.db) as s, patch.object(api,'send_test_smtp_message',return_value='sender@qq.com') as send:
            result=api.test_notification_smtp(admin={'role':'admin','tenant_id':'default'},
                req=api.NotificationSettingsTestRequest(smtp={'username':'sender@qq.com','password':'','from':'Fixture'}),session=s)
        self.assertTrue(result['ok']);self.assertEqual(send.call_args.args[0]['password'],'fixture-auth-code')

    def test_changing_sender_requires_new_secret(self):
        self.store()
        with Session(self.db) as s:
            with self.assertRaises(HTTPException) as err:
                api._save_notification_settings(s,{'username':'other@qq.com','password':''})
            self.assertEqual(err.exception.status_code,400)

    def test_read_settings_no_store_and_secret_presence_only(self):
        self.store()
        with Session(self.db) as s:
            response=Response()
            result=api.get_notification_settings(response=response,session=s,admin={'tenant_id':'default'})
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertTrue(result['smtp']['hasPassword']);self.assertNotIn('password',result['smtp'])


class VerificationSessionTest(DatabaseCase):
    def test_real_task_branch_binds_encrypted_context_before_result_sanitization(self):
        from server.clockin_preauthorization import ClockInPreauthorizationHooks
        from tests.test_alipay_clockin_verification import build_task_api_client, build_task_config
        from server.user_runtime import apply_execution_results_to_user
        client=build_task_api_client({'status':'verification_required'})
        hooks=ClockInPreauthorizationHooks(tenant_id='default',user_id=1,db_engine=self.db)
        with patch.object(task_runner,'upload_img',return_value=[]):
            result=task_runner.perform_clock_in(client,build_task_config(),forced_checkin_type='START',
                       target_time=dt.datetime(2026,10,21,8,30),preauthorization_hooks=hooks)
        sid=result['details']['verification_session_id']
        with Session(self.db) as s:
            user=s.get(User,1);apply_execution_results_to_user(user,[result],{})
            s.add(user);s.commit();s.refresh(user)
            serialized=json.dumps(user.last_execution_result)
            self.assertIn(sid,serialized)
            self.assertNotIn('registerUrl',serialized);self.assertNotIn('outRegisterNo',serialized)
        self.assertEqual(verification.session_links(self.user,sid,db_engine=self.db)['state'],'awaiting_verification')
        client.submit_clock_in.assert_called_once()

    def test_restart_context_encrypted_and_summary_has_no_links(self):
        sid=self.session_id()
        with Session(self.db) as s:
            stored=get_setting(s,verification.PREFIX+sid).value
            self.assertTrue(stored['payload'].startswith('enc$'))
            public=json.dumps(verification.list_sessions(s,self.user))
            self.assertNotIn('fixture-private',public);self.assertNotIn('payload',public)
        restored=verification.session_links(self.user,sid,db_engine=self.db)
        self.assertTrue(restored['qr_data_url'].startswith('data:image/png;base64,'))
        self.assertIn('fixture-private-link',restored['direct_url'])

    def test_other_account_and_other_tenant_cannot_open_or_check(self):
        sid=self.session_id()
        for other in (User(id=2,tenant_id='default',phone='other',password='x'),
                      User(id=1,tenant_id='other-tenant',phone='other',password='x')):
            with self.assertRaises(HTTPException) as err:
                verification.session_links(other,sid,db_engine=self.db)
            self.assertEqual(err.exception.status_code,404)
            with self.assertRaises(HTTPException) as err:
                verification.check_session(other,sid,db_engine=self.db)
            self.assertEqual(err.exception.status_code,404)

    def test_invalid_identifier_never_creates_lock_or_remote_request(self):
        with patch.object(verification,'acquire_task_lock') as lock:
            with self.assertRaises(HTTPException) as err:
                verification.check_session(self.user,'x'*2048,db_engine=self.db)
        self.assertEqual(err.exception.status_code,404);lock.assert_not_called()

    def test_verified_not_success_until_matching_record_and_never_resubmits(self):
        sid=self.session_id(); client=Mock()
        with Session(self.db) as s:
            user=s.get(User,1);user.last_status='Fail'
            user.last_execution_result=[{'task_type':'打卡','status':'fail','message':'需要本人验证',
                'details':{'attendance_date':'2026-10-21','target_type':'START','verification_type':'account'}}]
            s.add(user);s.commit()
        client.query_alipay_clockin_verification.return_value={'code':200,'data':True}
        client.get_checkin_records.return_value=[]
        with patch('server.coreApi.MainLogicApi.ApiClient',return_value=client), patch('server.attendance_confirmation.time.sleep'):
            checked=verification.check_session(self.user,sid,db_engine=self.db)
            self.assertEqual(checked['state'],'verified_pending_record')
            with Session(self.db) as s:
                user=s.get(User,1);self.assertEqual(user.last_status,'Pending')
                self.assertEqual(user.last_execution_result[0]['status'],'pending')
                self.assertEqual(user.last_execution_result[0]['details']['confirmation_state'],'verified_pending_record')
            self.force_check(sid)
            client.get_checkin_records.return_value=[{'type':'START','createTime':'2026-10-21 08:30:00'}]
            checked=verification.check_session(self.user,sid,db_engine=self.db)
        self.assertEqual(checked['state'],'record_confirmed')
        with Session(self.db) as s:
            self.assertEqual(s.get(User,1).last_status,'Success')
            self.assertEqual(s.get(User,1).last_run_time,'2026-10-21 08:30:00')
            self.assertEqual(get_setting(s,verification.PREFIX+sid).value['payload'],'')
        client.submit_clock_in.assert_not_called();client.login.assert_not_called()
        client.query_alipay_clockin_verification.assert_called_once()

    def test_http_success_false_data_is_not_verified(self):
        sid=self.session_id();client=Mock()
        client.query_alipay_clockin_verification.return_value={'code':200,'data':False}
        client.get_checkin_records.return_value=[]
        with patch('server.coreApi.MainLogicApi.ApiClient',return_value=client), patch('server.attendance_confirmation.time.sleep'):
            state=verification.check_session(self.user,sid,db_engine=self.db)
        self.assertEqual(state['state'],'awaiting_verification');self.assertFalse(state['verification_confirmed'])

    def test_face_only_checks_records_no_account_query(self):
        sid=self.session_id('face');client=Mock()
        client.get_checkin_records.return_value=[{'type':'START','createTime':'2026-10-21 08:30:00'}]
        with patch('server.coreApi.MainLogicApi.ApiClient',return_value=client):
            state=verification.check_session(self.user,sid,db_engine=self.db)
        self.assertEqual(state['state'],'record_confirmed');client.query_alipay_clockin_verification.assert_not_called()

    def test_expired_link_removed_but_server_record_can_still_confirm(self):
        sid=self.session_id()
        with Session(self.db) as s:
            row=get_setting(s,verification.PREFIX+sid);data=dict(row.value);data['expires_at']=0
            upsert_setting(s,verification.PREFIX+sid,data);s.commit()
        verification.cleanup_sessions()
        with self.assertRaises(HTTPException) as err:verification.session_links(self.user,sid,db_engine=self.db)
        self.assertEqual(err.exception.status_code,410)
        client=Mock();client.get_checkin_records.return_value=[{'type':'START','createTime':'2026-10-21 08:30:00'}]
        with patch('server.coreApi.MainLogicApi.ApiClient',return_value=client):state=verification.check_session(self.user,sid,db_engine=self.db)
        self.assertEqual(state['state'],'record_confirmed');client.query_alipay_clockin_verification.assert_not_called()


class ReconciliationTest(DatabaseCase):
    def test_nested_pending_totals_reconcile_without_erasing_other_day(self):
        pending={'status':'pending','task_type':'打卡','details':{'attendance_date':'2026-10-21','target_type':'START'}}
        parent={'status':'pending','task_type':'补卡','details':{'成功':0,'待确认':1},'items':[pending]}
        check={'target_type':'START','record_confirmed':True,'server_time':'2026-10-21 08:30:00'}
        values,changed=reconcile_results([parent],'2026-10-21',[check])
        self.assertTrue(changed);self.assertEqual(values[0]['status'],'success')
        self.assertEqual(values[0]['details']['待确认'],0);self.assertEqual(values[0]['details']['成功'],1)

    def test_preserves_unrelated_failure_and_wrong_date_type(self):
        attendance={'status':'pending','task_type':'打卡','details':{'attendance_date':'2026-10-21','target_type':'START'}}
        failed_report={'status':'fail','task_type':'日报','message':'报告失败'}
        checks=[{'target_type':'START','record_confirmed':True,'server_time':'2026-10-21 08:30:00'}]
        values,changed=reconcile_results([attendance,failed_report],'2026-10-20',checks)
        self.assertFalse(changed)
        values,changed=reconcile_results([attendance,failed_report],'2026-10-21',checks)
        self.assertTrue(changed);self.assertEqual(values[1],failed_report)
        from server.user_runtime import execution_status
        self.assertEqual(execution_status(values),'Fail')

    def test_monitor_recovers_once_reconciles_user_and_cancels_old_alert(self):
        client=Mock();client.get_checkin_records.return_value=[]
        now=dt.datetime(2026,10,21,9,tzinfo=task_status.TZ)
        push_states=[{'type':'SMTP','status':'sent'}]
        with patch('server.coreApi.MainLogicApi.ApiClient',return_value=client), \
             patch.object(task_runner,'_load_global_smtp_settings',return_value={}), \
             patch('server.util.MessagePush.MessagePusher.push',return_value=push_states) as push:
            task_status.detect_user(self.user,now)
            with Session(self.db) as s:
                row=get_setting(s,'attendance-monitor:1');data=dict(row.value)
                incident=data['checks'][0]['incident_id'];data['checked_at']=0
                upsert_setting(s,'attendance-monitor:1',data)
                upsert_setting(s,'mail-outbox:old-alert',{'status':'retry','payload':'enc$fixture',
                    'incident_id':incident,'incident_phase':'alert'});s.commit()
            client.get_checkin_records.return_value=[{'type':'START','createTime':'2026-10-21 08:30:00'}]
            task_status.detect_user(self.user,now)
            with Session(self.db) as s:
                row=get_setting(s,'attendance-monitor:1');data=dict(row.value);data['checked_at']=0
                upsert_setting(s,'attendance-monitor:1',data);s.commit()
                self.assertEqual(s.get(User,1).last_status,'Success')
                self.assertEqual(get_setting(s,'mail-outbox:old-alert').value['status'],'cancelled')
            task_status.detect_user(self.user,now)
        self.assertEqual(push.call_count,2)
        self.assertEqual(push.call_args.args[0][0]['task_type'],'异常恢复通知')
        client.submit_clock_in.assert_not_called()

    def test_unconfirmed_query_is_not_recovery(self):
        client=Mock();client.get_checkin_records.side_effect=TimeoutError()
        now=dt.datetime(2026,10,21,9,tzinfo=task_status.TZ)
        with patch('server.coreApi.MainLogicApi.ApiClient',return_value=client), \
             patch.object(task_runner,'_load_global_smtp_settings',return_value={}), \
             patch('server.util.MessagePush.MessagePusher.push',return_value=[{'type':'SMTP','status':'retry'}]) as push:
            task_status.detect_user(self.user,now)
            with Session(self.db) as s:
                row=get_setting(s,'attendance-monitor:1');value=dict(row.value);value['checked_at']=0
                upsert_setting(s,'attendance-monitor:1',value);s.commit()
            task_status.detect_user(self.user,now)
        self.assertEqual(push.call_count,1)
        with Session(self.db) as s:self.assertEqual(s.get(User,1).last_status,'Pending')


class ApiScopeTest(DatabaseCase):
    def test_summary_and_retrieval_have_distinct_permissions_and_no_store(self):
        from server.main import app
        from server.database import get_session
        from fastapi.testclient import TestClient
        sid=self.session_id()
        def session():
            with Session(self.db) as s:yield s
        previous=dict(app.dependency_overrides)
        try:
            app.dependency_overrides[get_session]=session
            app.dependency_overrides[api.get_auth_payload]=lambda:{'role':'admin','sub':'fixture','tenant_id':'default'}
            client=TestClient(app,base_url='http://127.0.0.1')
            response=client.get(f'/api/users/1/verification-sessions/{sid}')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertNotIn('outRegisterNo',response.json())
            summary=client.get('/api/users/1/task-status')
            self.assertNotIn('fixture-private',summary.text)
            app.dependency_overrides[api.get_auth_payload]=lambda:{'role':'viewer','sub':'fixture','tenant_id':'default'}
            self.assertEqual(client.get(f'/api/users/1/verification-sessions/{sid}').status_code,403)
        finally:
            app.dependency_overrides.clear();app.dependency_overrides.update(previous)


if __name__=='__main__':unittest.main()
