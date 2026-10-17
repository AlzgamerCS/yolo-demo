"""Audio lifecycle and WebSocket access checks without recording real inputs."""
import threading
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from yolo_studio.audio import AudioHub, input_devices
from yolo_studio.web.routes.audio import router


class FakeStream:
    active = True

    def stop(self):
        self.active = False

    def close(self):
        self.active = False


class SyntheticHub(AudioHub):
    def resolve_device(self, device):
        return 1 if device is None else device

    def open(self, device):
        self.stream, self.device = FakeStream(), device

    async def subscribe(self, device=None):
        subscriber, rate = await super().subscribe(device)
        self.publish(b'\x00\x00' * 320, 320, None, None)
        return subscriber, rate


class CaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_stereo_microphone_uses_active_channel_without_cancellation(self):
        hub = SyntheticHub()
        subscriber, _ = await hub.subscribe()
        subscriber.get_nowait()
        hub.channels = 2
        hub.publish(struct.pack('<4h', 0, 1000, 0, -1000), 2, None, None)
        self.assertEqual(struct.unpack('<2h', subscriber.get_nowait()), (1000, -1000))
        hub.publish(struct.pack('<4h', 1000, -1000, 2000, -2000), 2, None, None)
        self.assertEqual(struct.unpack('<2h', subscriber.get_nowait()), (1000, 2000))
        await hub.unsubscribe(subscriber)

    async def test_shared_capture_and_bounded_slow_listener(self):
        hub = SyntheticHub()
        first, rate = await hub.subscribe()
        second, _ = await hub.subscribe()
        self.assertEqual(rate, 16000)
        stream = hub.stream
        for value in range(20):
            hub.publish(bytes([value]), 1, None, None)
        self.assertEqual(first.qsize(), 5)
        self.assertEqual(list(first.queue), [bytes([value]) for value in range(15, 20)])
        self.assertEqual(second.qsize(), 5)
        with self.assertRaisesRegex(ValueError, 'different server microphone'):
            await hub.subscribe(7)
        await hub.unsubscribe(first)
        self.assertTrue(stream.active)
        await hub.unsubscribe(second)
        self.assertFalse(stream.active)
        self.assertIsNone(hub.stream)

    async def test_open_failure_does_not_add_listener(self):
        hub = AudioHub()
        with patch.object(hub, 'resolve_device', return_value=1), patch.object(hub, 'open', side_effect=RuntimeError('No input')):
            with self.assertRaisesRegex(RuntimeError, 'No input'):
                await hub.subscribe()
        self.assertEqual(hub.subscribers, ())


class DeviceTests(unittest.TestCase):
    def test_windows_shows_active_endpoints_without_legacy_duplicates(self):
        devices = [{'name': 'Input mapper', 'hostapi': 0, 'max_input_channels': 2},
                   {'name': 'Realtek', 'hostapi': 0, 'max_input_channels': 2},
                   {'name': 'Realtek', 'hostapi': 1, 'max_input_channels': 2},
                   {'name': 'Speakers', 'hostapi': 1, 'max_input_channels': 0}]
        apis = [{'name': 'MME', 'default_input_device': 1},
                {'name': 'Windows WASAPI', 'default_input_device': 2}]
        with patch('sounddevice.query_devices', return_value=devices), \
             patch('sounddevice.query_hostapis', return_value=apis), \
             patch('sounddevice.default.device', [1, 3]), \
             patch('yolo_studio.audio.sys.platform', 'win32'):
            result = input_devices()
        self.assertEqual([device['value'] for device in result['devices']], ['2'])
        self.assertEqual(result['default_device'], 2)
        self.assertEqual(result['default_label'], 'Realtek')

    def test_capture_uses_native_rate_and_microphone_channels(self):
        hub = AudioHub()
        info = {'name': 'Realtek', 'default_samplerate': 48000, 'max_input_channels': 2}
        with patch('sounddevice.query_devices', return_value=info), \
             patch('sounddevice.check_input_settings'), \
             patch('sounddevice.RawInputStream') as stream:
            hub.open(2)
        self.assertEqual(stream.call_args.kwargs['channels'], 2)
        self.assertEqual(stream.call_args.kwargs['samplerate'], 48000)
        self.assertEqual(hub.sample_rate, 48000)
        self.assertEqual(hub.device_name, 'Realtek')


class SocketTests(unittest.TestCase):
    def setUp(self):
        self.engine = SimpleNamespace(condition=threading.Condition(), active=True,
                                      closed=False, phase='running', generation=3,
                                      config=SimpleNamespace(source='laptop'))
        self.hub = SyntheticHub()
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.state.audio = self.hub
        self.app.state.sessions = SimpleNamespace(lock=threading.Lock(), items={'test': (self.engine, 0)})
        self.headers = {'origin': 'http://testserver'}

    def test_pcm_delivery_and_source_switch_releases_microphone(self):
        with TestClient(self.app) as client:
            client.cookies.set('yolo_session', 'test')
            with client.websocket_connect('/api/audio', headers=self.headers) as socket:
                self.assertEqual(socket.receive_json()['sample_rate'], 16000)
                self.assertEqual(len(socket.receive_bytes()), 640)
                self.engine.config.source = 'browser'
                with self.assertRaises(WebSocketDisconnect):
                    socket.receive_bytes()
        self.assertIsNone(self.hub.stream)
        self.assertEqual(self.hub.subscribers, ())

    def test_disconnect_releases_microphone(self):
        with TestClient(self.app) as client:
            client.cookies.set('yolo_session', 'test')
            with client.websocket_connect('/api/audio', headers=self.headers) as socket:
                socket.receive_json()
                socket.receive_bytes()
        self.assertIsNone(self.hub.stream)

    def test_stop_and_configuration_change_end_listening(self):
        for attribute, value in [('active', False), ('generation', 4)]:
            with self.subTest(attribute=attribute):
                self.engine.active, self.engine.generation = True, 3
                with TestClient(self.app) as client:
                    client.cookies.set('yolo_session', 'test')
                    with client.websocket_connect('/api/audio', headers=self.headers) as socket:
                        socket.receive_json()
                        socket.receive_bytes()
                        setattr(self.engine, attribute, value)
                        with self.assertRaises(WebSocketDisconnect):
                            socket.receive_bytes()
                self.assertIsNone(self.hub.stream)

    def test_capture_error_is_reported_to_listener(self):
        with patch.object(self.hub, 'open', side_effect=RuntimeError('Microphone permission denied')):
            with TestClient(self.app) as client:
                client.cookies.set('yolo_session', 'test')
                with client.websocket_connect('/api/audio', headers=self.headers) as socket:
                    self.assertIn('permission denied', socket.receive_json()['error'])
                    with self.assertRaises(WebSocketDisconnect):
                        socket.receive_bytes()
        self.assertIsNone(self.hub.stream)

    def test_wrong_origin_missing_session_and_stopped_source_rejected(self):
        with TestClient(self.app) as client:
            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect('/api/audio', headers=self.headers):
                    pass
            client.cookies.set('yolo_session', 'test')
            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect('/api/audio', headers={'origin': 'https://unrelated.invalid'}):
                    pass
            self.engine.active = False
            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect('/api/audio', headers=self.headers):
                    pass


if __name__ == '__main__':
    unittest.main()
