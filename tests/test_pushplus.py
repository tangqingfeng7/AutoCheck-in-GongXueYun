import json
import os
import unittest
from unittest.mock import Mock, patch

import requests
from fastapi import Response
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from server import api
from server.pushplus_settings import load_pushplus, save_pushplus, sanitize_pushplus, resolve_pushplus
from server.pushplus_delivery import send_message, upload_qr, PushPlusError
from server.settings_store import get_setting
from server.user_runtime import build_effective_push_notifications
from server.util.MessagePush import MessagePusher


class PushPlusSettingsTest(unittest.TestCase):
    def setUp(self):
        self.db = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(self.db)
        self.env = patch.dict(os.environ, {'USER_PASSWORD_KEY': 'fixture-pushplus-key'})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.db.dispose()

    def test_credentials_encrypted_masked_and_blank_preserved(self):
        with Session(self.db) as session:
            clean = save_pushplus(session, {'enabled': True, 'token': 'fixture-token', 'secretKey': 'fixture-secret', 'uploadQr': True})
            session.commit()
            self.assertTrue(clean['hasToken']); self.assertTrue(clean['hasSecretKey'])
            self.assertNotIn('fixture-', json.dumps(clean))
            stored = get_setting(session, 'pushplus').value
            self.assertTrue(stored['token'].startswith('enc$'))
            self.assertTrue(stored['secretKey'].startswith('enc$'))
            save_pushplus(session, {'token': '', 'secretKey': ''})
            self.assertEqual(load_pushplus(session)['token'], 'fixture-token')
            self.assertFalse(load_pushplus(session, 'other')['enabled'])

    def test_read_api_no_store_and_no_credentials(self):
        with Session(self.db) as session:
            save_pushplus(session, {'enabled': True, 'token': 'fixture-token'})
            response = Response()
            result = api.get_notification_settings(response=response, session=session, admin={'tenant_id': 'default'})
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertNotIn('fixture-token', json.dumps(result))
            self.assertTrue(result['pushplus']['hasToken'])

    def test_requires_encryption_key(self):
        with patch.dict(os.environ, {'USER_PASSWORD_KEY': '', 'FERNET_KEY': '', 'APP_ENV': 'development'}), Session(self.db) as session:
            with self.assertRaises(ValueError):
                save_pushplus(session, {'token': 'fixture-token'})

    def test_requires_token_and_upload_secret(self):
        for value in ({'enabled': True}, {'token': 'fixture', 'uploadQr': True}):
            with self.assertRaises(ValueError):
                resolve_pushplus(value, {})

    def test_corrupt_ciphertext_fails_closed(self):
        from server.settings_store import upsert_setting
        with Session(self.db) as session:
            upsert_setting(session, 'pushplus', {'enabled': True, 'token': 'enc$invalid'})
            self.assertEqual(load_pushplus(session)['token'], '')

    def test_disable_keeps_secret_and_smtp_unchanged(self):
        with Session(self.db) as session:
            api._save_notification_settings(session, {'username': 'fixture@qq.com', 'password': 'fixture-mail'})
            save_pushplus(session, {'enabled': True, 'token': 'fixture-token'})
            clean = save_pushplus(session, {'enabled': False})
            self.assertFalse(clean['enabled']); self.assertTrue(clean['hasToken'])
            self.assertEqual(api._get_notification_settings(session)['smtp']['password'], 'fixture-mail')


class PushPlusDeliveryTest(unittest.TestCase):
    config = {'type': 'PushPlus', 'enabled': True, 'token': 'fixture-token'}
    result = {'status': 'pending', 'task_type': '打卡', 'message': '待授权', 'details': {
        'verification_type': 'account', 'registerUrl': 'alipays://platformapi/startapp?appId=fixture', 'outRegisterNo': 'private-fixture'}}

    def test_provider_acceptance_not_delivery(self):
        response = Mock(status_code=200); response.json.return_value = {'code': 200}
        with patch('server.pushplus_delivery.requests.post', return_value=response) as post:
            self.assertEqual(send_message(self.config, 'title', 'content'), 'accepted')
        self.assertFalse(post.call_args.kwargs['allow_redirects'])
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs['json']['channel'], 'wechat')

    def test_provider_rejection_does_not_leak_payload(self):
        response = Mock(status_code=200); response.json.return_value = {'code': 500, 'msg': 'fixture-token'}
        with patch('server.pushplus_delivery.requests.post', return_value=response):
            with self.assertRaises(PushPlusError) as error:
                send_message(self.config, 'title', 'content')
            self.assertNotIn('fixture-token', str(error.exception))

    def test_authorization_link_without_public_qr_service(self):
        with patch('server.pushplus_delivery.send_message', return_value='accepted') as send, patch('server.pushplus_delivery.upload_qr') as upload:
            states = MessagePusher([self.config]).push([self.result])
        self.assertEqual(states, [{'type': 'PushPlus', 'status': 'accepted'}])
        upload.assert_not_called()
        content = send.call_args.args[2]
        self.assertIn('ds.alipay.com', content)
        self.assertNotIn('private-fixture', content)
        self.assertNotIn('quickchart', content)
        self.assertTrue(content.endswith('</body></html>'))

    def test_local_qr_uploaded_only_when_opted_in(self):
        with patch('server.pushplus_delivery.send_message', return_value='accepted') as send, patch('server.pushplus_delivery.upload_qr', return_value='https://pic.pushplus.plus/test.png') as upload:
            MessagePusher([{**self.config, 'secretKey': 'fixture-secret', 'uploadQr': True}]).push([self.result])
        self.assertTrue(upload.call_args.args[1].startswith(b'\x89PNG'))
        self.assertIn('https://pic.pushplus.plus/test.png', send.call_args.args[2])

    def test_upload_failure_still_sends_authorization_link(self):
        with patch('server.pushplus_delivery.send_message', return_value='accepted') as send, patch('server.pushplus_delivery.upload_qr', side_effect=PushPlusError):
            states = MessagePusher([{**self.config, 'secretKey': 'fixture-secret', 'uploadQr': True}]).push([self.result])
        self.assertEqual(states[0]['status'], 'accepted')
        self.assertIn('ds.alipay.com', send.call_args.args[2])

    def test_timeout_uncertain_and_smtp_still_runs(self):
        with patch('server.pushplus_delivery.send_message', side_effect=requests.Timeout) as send, patch.object(MessagePusher, '_smtp_push', return_value='queued') as smtp:
            states = MessagePusher([self.config, {'type': 'SMTP', 'enabled': True}]).push([{'status': 'success', 'task_type': '打卡'}])
        self.assertEqual([s['status'] for s in states], ['uncertain', 'queued'])
        self.assertEqual(send.call_count, 1); smtp.assert_called_once()

    def test_disabled_or_skipped_does_not_send(self):
        with patch('server.pushplus_delivery.send_message') as send:
            MessagePusher([{**self.config, 'enabled': False}]).push([self.result])
            MessagePusher([self.config]).push([{'status': 'skip'}])
        send.assert_not_called()

    def test_build_keeps_existing_channels(self):
        services = build_effective_push_notifications(user_push=[], smtp_settings={}, pushplus_settings=self.config)
        self.assertEqual([s['type'] for s in services], ['Server', 'SMTP', 'PushPlus'])
        self.assertTrue(services[-1]['enabled'])

    def test_upload_rejects_private_or_untrusted_destination(self):
        auth = Mock(status_code=200); auth.json.return_value = {'code': 200, 'data': {'accessKey': 'fixture-key'}}
        ticket = Mock(status_code=200); ticket.json.return_value = {'code': 200, 'data': {'uploadUrl': 'https://127.0.0.1/', 'uploadToken': 'fixture'}}
        with patch('server.pushplus_delivery.requests.request', side_effect=[auth, ticket]), patch('server.pushplus_delivery.requests.post') as post:
            with self.assertRaises(PushPlusError):
                upload_qr({**self.config, 'secretKey': 'fixture-secret'}, b'png')
            post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
