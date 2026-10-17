"""Client audio relay isolation, permissions, bounds, and immediate revocation."""

import struct
import threading
import unittest
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from yolo_studio.client_audio import ClientAudioBuffer
from yolo_studio.config import Config
from yolo_studio.web.routes.client_audio import router
from yolo_studio.web.routes.controls import router as controls


def engine(identifier):
    state = SimpleNamespace(
        condition=threading.Condition(),
        active=True,
        closed=False,
        generation=1,
        phase="running",
        public_id=identifier,
        config=Config(source="browser"),
        client_audio=ClientAudioBuffer(),
        raw_jpeg=None,
    )
    state.status = lambda: {"generation": state.generation, "config": state.config.model_dump()}
    return state


class ClientAudioTests(unittest.TestCase):
    def setUp(self):
        self.first, self.second = engine("first"), engine("second")
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.include_router(controls)
        self.app.state.sessions = SimpleNamespace(
            lock=threading.Lock(), items={"a": (self.first, 0), "b": (self.second, 0)}
        )

        @self.app.middleware("http")
        async def attach(request, call_next):
            request.state.engine = (
                self.first if request.cookies.get("yolo_session") == "a" else self.second
            )
            return await call_next(request)

        self.headers = {"origin": "http://localhost"}

    def client(self):
        return TestClient(self.app, base_url="http://localhost", client=("127.0.0.1", 50123))

    def test_default_sharing_and_buffer_bound(self):
        self.assertTrue(Config().share_with_operator)
        self.assertTrue(Config().share_audio)
        for index in range(50):
            self.first.client_audio.push(bytes([index]))
        self.assertEqual(len(self.first.client_audio.packets), 8)
        self.assertEqual(self.first.client_audio.packets[-1][2], bytes([49]))

    def test_two_clients_are_isolated_and_mute_is_immediate(self):
        a, b = struct.pack("<320h", *([1000] * 320)), struct.pack("<320h", *([-2000] * 320))
        with self.client() as client:
            client.cookies.set("yolo_session", "a")
            with client.websocket_connect(
                "ws://localhost/api/client-audio?generation=1", headers=self.headers
            ) as uplink_a:
                uplink_a.send_json({"sample_rate": 16000})
                uplink_a.send_bytes(a)
                client.cookies.set("yolo_session", "b")
                with client.websocket_connect(
                    "ws://localhost/api/client-audio?generation=1", headers=self.headers
                ) as uplink_b:
                    uplink_b.send_json({"sample_rate": 16000})
                    uplink_b.send_bytes(b)
                    with client.websocket_connect(
                        "ws://localhost/api/operator/audio/first", headers=self.headers
                    ) as down_a:
                        self.assertEqual(down_a.receive_json()["sample_rate"], 16000)
                        self.assertEqual(down_a.receive_bytes(), a)
                        with client.websocket_connect(
                            "ws://localhost/api/operator/audio/second", headers=self.headers
                        ) as down_b:
                            down_b.receive_json()
                            self.assertEqual(down_b.receive_bytes(), b)
                            client.cookies.set("yolo_session", "a")
                            response = client.post(
                                "/api/sharing",
                                json={"share_with_operator": True, "share_audio": False},
                            )
                            self.assertEqual(response.json()["generation"], 1)
                            with self.assertRaises(WebSocketDisconnect):
                                down_a.receive_bytes()
                            self.assertFalse(self.first.client_audio.packets)
                            uplink_b.send_bytes(b)
                            self.assertEqual(down_b.receive_bytes(), b)
        self.assertFalse(self.second.client_audio.packets)

    def test_rejects_stale_generation_and_unshared_microphone(self):
        with self.client() as client:
            client.cookies.set("yolo_session", "a")
            for path in ["/api/client-audio?generation=0", "/api/operator/audio/missing"]:
                with self.subTest(path=path), self.assertRaises(WebSocketDisconnect):
                    with client.websocket_connect("ws://localhost" + path, headers=self.headers):
                        pass
            self.first.config.share_audio = False
            for path in ["/api/client-audio?generation=1", "/api/operator/audio/first"]:
                with self.subTest(path=path), self.assertRaises(WebSocketDisconnect):
                    with client.websocket_connect("ws://localhost" + path, headers=self.headers):
                        pass

    def test_wrong_origin_and_public_monitor_are_rejected(self):
        with self.client() as client:
            client.cookies.set("yolo_session", "a")
            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect(
                    "ws://localhost/api/client-audio?generation=1",
                    headers={"origin": "https://unrelated.invalid"},
                ):
                    pass
        with TestClient(
            self.app, base_url="https://demo.trycloudflare.com", client=("127.0.0.1", 50123)
        ) as public:
            with self.assertRaises(WebSocketDisconnect):
                with public.websocket_connect(
                    "wss://demo.trycloudflare.com/api/operator/audio/first",
                    headers={"origin": "https://demo.trycloudflare.com"},
                ):
                    pass

    def test_bad_audio_packet_is_rejected_and_buffer_cleared(self):
        with self.client() as client:
            client.cookies.set("yolo_session", "a")
            with client.websocket_connect(
                "ws://localhost/api/client-audio?generation=1", headers=self.headers
            ) as socket:
                socket.send_json({"sample_rate": 16000})
                socket.send_bytes(b"odd")
                with self.assertRaises(WebSocketDisconnect):
                    socket.receive_bytes()
        self.assertFalse(self.first.client_audio.packets)


if __name__ == "__main__":
    unittest.main()
