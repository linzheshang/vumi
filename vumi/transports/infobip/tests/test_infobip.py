"""Test for vumi.transport.infobip.infobip."""

import json

from twisted.internet.defer import inlineCallbacks, returnValue

from vumi.transports.tests.utils import TransportTestCase
from vumi.utils import http_request
from vumi.transports.infobip.infobip import InfobipTransport
from vumi.message import TransportUserMessage
from vumi.tests.utils import LogCatcher


class TestInfobipUssdTransport(TransportTestCase):

    transport_name = 'test_infobip'
    transport_class = InfobipTransport

    @inlineCallbacks
    def setUp(self):
        yield super(TestInfobipUssdTransport, self).setUp()
        config = {
            'transport_name': 'test_infobip',
            'transport_type': 'ussd',
            'web_path': "/session/",
            'web_port': 0,
            }
        self.transport = yield self.get_transport(config)
        self.transport_url = self.transport.get_transport_url()
        yield self.transport.session_manager.redis._purge_all()  # just in case

    DEFAULT_START_DATA = {
        "msisdn": "385955363443",
        "imsi": "429011234567890",
        "shortCode": "*123#1#",
        "optional": "o=1",
        "ussdGwId": "11",
        "language": None,
        }

    DEFAULT_SESSION_DATA = {
        "start": DEFAULT_START_DATA,
        "response": DEFAULT_START_DATA,
        "end": {"reason": "ok", "exitCode": 0},
        "status": None,
        }

    SESSION_HTTP_METHOD = {
        "end": "PUT",
        }

    @inlineCallbacks
    def make_request(self, session_type, session_id, reply=None,
                     continue_session=True, expect_msg=True,
                     defer_response=False, **kw):
        url_suffix = "session/%s/%s" % (session_id, session_type)
        method = self.SESSION_HTTP_METHOD.get(session_type, "POST")
        request_data = self.DEFAULT_SESSION_DATA[session_type].copy()
        request_data.update(kw)
        deferred_req = http_request(self.transport_url + url_suffix,
                                    json.dumps(request_data), method=method)
        if not expect_msg:
            msg = None
        else:
            [msg] = yield self.wait_for_dispatched_messages(1)
            self.clear_dispatched_messages()
            msg = TransportUserMessage(**msg.payload)
            if reply is not None:
                reply_msg = msg.reply(reply, continue_session=continue_session)
                self.dispatch(reply_msg)

        if defer_response:
            response = deferred_req
        else:
            response = yield deferred_req
        returnValue((msg, response))

    @inlineCallbacks
    def test_start(self):
        msg, response = yield self.make_request("start", 1, text="hello there",
                                                reply="hello yourself")
        self.assertEqual(msg['content'], 'hello there')
        self.assertEqual(msg['session_event'],
                         TransportUserMessage.SESSION_NEW)

        correct_response = {
            "shouldClose": False,
            "responseExitCode": 200,
            "ussdMenu": "hello yourself",
            "responseMessage": "",
            }
        self.assertEqual(json.loads(response), correct_response)

    @inlineCallbacks
    def test_start_twice(self):
        msg, response = yield self.make_request("start", 1, text="hello there",
                                                reply="hello yourself")
        msg, response = yield self.make_request("start", 1, text="hello again",
                                                expect_msg=False)

        correct_response = {
            'responseExitCode': 400,
            'responseMessage': "USSD session '1' already started",
            }
        self.assertEqual(json.loads(response), correct_response)

    @inlineCallbacks
    def test_response_with_close(self):
        msg, response = yield self.make_request("start", 1, text="Hi",
                                                reply="Hi!")
        msg, response = yield self.make_request("response", 1, text="More?",
                                                reply="No thanks.",
                                                continue_session=False)

        self.assertEqual(msg['content'], 'More?')
        self.assertEqual(msg['session_event'],
                         TransportUserMessage.SESSION_RESUME)

        correct_response = {
            "shouldClose": True,
            "responseExitCode": 200,
            "ussdMenu": "No thanks.",
            "responseMessage": "",
            }
        self.assertEqual(json.loads(response), correct_response)

    @inlineCallbacks
    def test_response_for_invalid_session(self):
        msg, response = yield self.make_request("response", 1,
                                                expect_msg=False)

        correct_response = {
            'responseExitCode': 400,
            'responseMessage': "Invalid USSD session '1'",
            }
        self.assertEqual(json.loads(response), correct_response)

    @inlineCallbacks
    def test_end(self):
        msg, response = yield self.make_request("start", 1, text='Bye!',
                                                reply="Barp")
        msg, response = yield self.make_request("end", 1)

        self.assertEqual(msg['content'], None)
        self.assertEqual(msg['session_event'],
                         TransportUserMessage.SESSION_CLOSE)

        correct_response = {
            "responseExitCode": 200,
            "responseMessage": "",
            }
        self.assertEqual(json.loads(response), correct_response)

    @inlineCallbacks
    def test_end_for_invalid_session(self):
        msg, response = yield self.make_request("end", 1,
                                                expect_msg=False)

        correct_response = {
            'responseExitCode': 400,
            'responseMessage': "Invalid USSD session '1'",
            }
        self.assertEqual(json.loads(response), correct_response)

    @inlineCallbacks
    def test_status_for_active_session(self):
        msg, response = yield self.make_request("start", 1, text="Hi",
                                                reply="Boop")
        response = yield http_request(
            self.transport_url + "session/1/status", "", method="GET")
        correct_response = {
            'responseExitCode': 200,
            'responseMessage': '',
            'sessionActive': True,
            }
        self.assertEqual(json.loads(response), correct_response)

    @inlineCallbacks
    def test_status_for_inactive_session(self):
        response = yield http_request(
            self.transport_url + "session/1/status", "", method="GET")
        correct_response = {
            'responseExitCode': 200,
            'responseMessage': '',
            'sessionActive': False,
            }
        self.assertEqual(json.loads(response), correct_response)

    @inlineCallbacks
    def test_non_json_content(self):
        response = yield http_request(self.transport_url + "session/1/start",
                                      "not json at all", method="POST")
        correct_response = {
            'responseExitCode': 400,
            'responseMessage': 'Invalid JSON',
            }
        self.assertEqual(json.loads(response), correct_response)

    @inlineCallbacks
    def test_start_without_text(self):
        msg, response = yield self.make_request("start", 1,
                                                expect_msg=False)
        correct_response = {
            'responseExitCode': 400,
            'responseMessage': "Missing required JSON field:"
                               " KeyError('text',)",
            }
        self.assertEqual(json.loads(response), correct_response)

    @inlineCallbacks
    def test_response_without_text(self):
        msg, response = yield self.make_request("start", 1, text="Hi!",
                                                reply="Moo")
        msg, response = yield self.make_request("response", 1,
                                                expect_msg=False)
        correct_response = {
            'responseExitCode': 400,
            'responseMessage': "Missing required JSON field:"
                               " KeyError('text',)",
            }
        self.assertEqual(json.loads(response), correct_response)

    @inlineCallbacks
    def test_start_without_msisdn(self):
        json_dict = {
            'text': 'Oops. No msisdn.',
            }
        response = yield http_request(self.transport_url + "session/1/start",
                                      json.dumps(json_dict), method='POST')
        correct_response = {
            'responseExitCode': 400,
            'responseMessage': "Missing required JSON field:"
                               " KeyError('msisdn',)",
            }
        self.assertEqual(json.loads(response), correct_response)

    @inlineCallbacks
    def test_outbound_non_reply_logs_error(self):
        msg = TransportUserMessage(to_addr="1234", from_addr="5678",
                                   transport_name="test_infobip",
                                   transport_type="ussd",
                                   transport_metadata={})

        with LogCatcher() as logger:
            yield self.dispatch(msg)
            [error] = logger.errors

        expected_error = ("Infobip transport cannot process outbound message"
                          " that is not a reply: %s" % (msg['message_id'],))

        [errmsg] = error['message']
        self.assertTrue(expected_error in errmsg)
        [nack] = yield self.wait_for_dispatched_events(1)
        self.assertEqual(nack['user_message_id'], msg['message_id'])
        self.assertEqual(nack['nack_reason'], expected_error)

    @inlineCallbacks
    def test_ack(self):
        msg, response = yield self.make_request(
            "start", 1, text="Hi!", reply="Moo")
        [event] = yield self.wait_for_dispatched_events(1)
        [reply] = yield self.wait_for_dispatched_outbound(1)

        self.assertEqual(event["event_type"], "ack")
        self.assertEqual(event["user_message_id"], reply["message_id"])

    @inlineCallbacks
    def test_reply_failure(self):
        msg, deferred_req = yield self.make_request("start", 1, text="Hi!",
                                                    defer_response=True)
        # finish message so reply will fail
        self.transport.finish_request(msg['message_id'], "Done")
        reply = msg.reply("Ping")

        with LogCatcher() as logger:
            yield self.dispatch(reply)
            [error] = logger.errors

        expected_error = ("Infobip transport could not find original request"
                          " when attempting to reply.")

        [errmsg] = error['message']
        self.assertTrue(expected_error in errmsg)

        [nack] = yield self.wait_for_dispatched_events(1)
        [nack] = yield self.wait_for_dispatched_events(1)
        self.assertEqual(nack['user_message_id'], reply['message_id'])
        self.assertEqual(nack['nack_reason'], expected_error)
