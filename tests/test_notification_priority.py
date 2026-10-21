import unittest
from unittest.mock import Mock, patch

import requests

from server.pushplus_delivery import confirm_delivery, send_message, PushPlusError
from server.pushplus_settings import resolve_pushplus
from server.user_runtime import build_effective_push_notifications
from server.util.MessagePush import MessagePusher


class NotificationPriorityTest(unittest.TestCase):
    result = [{'status': 'success', 'task_type': 'fixture', 'message': 'fixture'}]

    def services(self):
        return build_effective_push_notifications(user_push=[{'type': 'SMTP', 'enabled': True, 'to': 'fixture@example.com'}],
            smtp_settings={'enabled': True}, pushplus_settings={
                'enabled': True, 'token': 'fixture-token', 'clawbotEnabled': True, 'fallbackEnabled': True})

    def check_chain(self, side_effect, expected):
        trace = []
        def online(config, title, content):
            trace.append(config['type'])
            value = side_effect[len(trace) - 1]
            if isinstance(value, Exception):
                raise value
            return value
        def mail(*args):
            trace.append('SMTP')
            return 'queued'
        with patch('server.pushplus_delivery.send_message', side_effect=online), patch.object(MessagePusher, '_smtp_push', side_effect=mail):
            states = MessagePusher(self.services()).push(self.result)
        self.assertEqual(trace, expected)
        return states

    def test_clawbot_confirmed_stops_chain(self):
        self.check_chain(['provider_sent'], ['ClawBot'])

    def test_clawbot_failed_uses_public_account(self):
        self.check_chain([PushPlusError('fixture'), 'provider_sent'], ['ClawBot', 'PushPlus'])

    def test_both_rejected_use_mail(self):
        self.check_chain([PushPlusError('fixture'), PushPlusError('fixture')], ['ClawBot', 'PushPlus', 'SMTP'])

    def test_accepted_is_not_success_and_falls_back(self):
        states = self.check_chain(['accepted', 'accepted'], ['ClawBot', 'PushPlus', 'SMTP'])
        self.assertEqual([s['status'] for s in states], ['accepted', 'accepted', 'queued'])

    def test_timeout_no_replay_uses_next_channels(self):
        self.check_chain([requests.Timeout(), 'provider_sent'], ['ClawBot', 'PushPlus'])

    def test_disabled_clawbot_skipped(self):
        services = self.services()
        for cfg in services:
            if cfg['type'] == 'ClawBot': cfg['enabled'] = False
        with patch('server.pushplus_delivery.send_message', return_value='provider_sent') as send, patch.object(MessagePusher, '_smtp_push') as mail:
            MessagePusher(services).push(self.result)
        self.assertEqual(send.call_args.args[0]['type'], 'PushPlus'); mail.assert_not_called()

    def test_all_skipped_no_channel_called(self):
        with patch('server.pushplus_delivery.send_message') as send, patch.object(MessagePusher, '_smtp_push') as mail:
            self.assertEqual(MessagePusher(self.services()).push([{'status': 'skip'}]), [])
        send.assert_not_called(); mail.assert_not_called()

    def test_settings_flags_preserved(self):
        config = resolve_pushplus({'clawbotEnabled': True, 'fallbackEnabled': True}, {'token': 'fixture-token'})
        self.assertTrue(config['clawbotEnabled']); self.assertTrue(config['fallbackEnabled'])

    def test_actual_send_payload_selects_clawbot(self):
        response = Mock(status_code=200); response.json.return_value = {'code': 200}
        with patch('server.pushplus_delivery.requests.post', return_value=response) as post:
            send_message({'token': 'fixture', 'type': 'ClawBot'}, 'title', 'html')
        self.assertEqual(post.call_args.kwargs['json']['channel'], 'clawbot')

    def test_provider_confirmation_requires_status_two(self):
        auth = Mock(); auth.json.return_value = {'code': 200, 'data': {'accessKey': 'fixture-access'}}
        for status, expected in [(2, 'provider_sent'), (3, 'failed'), (1, 'accepted')]:
            response = Mock(); response.json.return_value = {'code': 200, 'data': {'status': status}}
            with patch('server.pushplus_delivery.requests.post', return_value=auth), patch('server.pushplus_delivery.requests.get', return_value=response) as get, patch('server.pushplus_delivery.time.sleep'):
                self.assertEqual(confirm_delivery({'token': 'fixture', 'secretKey': 'fixture'}, 'short-fixture'), expected)
                self.assertLessEqual(get.call_count, 3)

    def test_invalid_key_or_no_receipt_remains_unknown(self):
        self.assertEqual(confirm_delivery({}, None), 'accepted')
        auth = Mock(); auth.json.return_value = {'code': 401}
        with patch('server.pushplus_delivery.requests.post', return_value=auth), patch('server.pushplus_delivery.requests.get') as get:
            self.assertEqual(confirm_delivery({'token': 'fixture', 'secretKey': 'fixture'}, 'short-fixture'), 'accepted')
        get.assert_not_called()

    def test_confirmation_timeout_is_unknown(self):
        with patch('server.pushplus_delivery.requests.post', side_effect=requests.Timeout):
            self.assertEqual(confirm_delivery({'token': 'fixture', 'secretKey': 'fixture'}, 'short-fixture'), 'accepted')


if __name__ == '__main__':
    unittest.main()
