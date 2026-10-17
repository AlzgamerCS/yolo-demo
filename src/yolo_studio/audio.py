"""Shared, on-demand server microphone capture with bounded listener buffers."""

import asyncio
import queue
import sys

import numpy as np


def input_devices():
    """Enumerate inputs without opening or recording the microphone."""
    try:
        import sounddevice as sd

        inputs = [
            (index, info)
            for index, info in enumerate(sd.query_devices())
            if info["max_input_channels"] > 0
        ]
        apis = sd.query_hostapis()
        # Windows exposes each physical input through multiple legacy APIs.
        # WASAPI lists the active Windows endpoints without mapper/driver aliases.
        modern = [
            (index, info)
            for index, info in inputs
            if apis[info["hostapi"]]["name"] == "Windows WASAPI"
        ]
        if sys.platform == "win32" and modern:
            inputs = modern
        default = int(sd.default.device[0])
        if inputs and default not in [index for index, _ in inputs]:
            api = apis[inputs[0][1]["hostapi"]]
            default = int(api["default_input_device"])
        if inputs and default not in [index for index, _ in inputs]:
            default = inputs[0][0]
        devices = [
            {"value": str(index), "label": info["name"], "default": index == default}
            for index, info in inputs
        ]
        label = next((info["name"] for index, info in inputs if index == default), "")
        return {
            "available": bool(devices),
            "devices": devices,
            "default_device": default,
            "default_label": label,
            "error": "",
        }
    except Exception as exc:
        return {"available": False, "devices": [], "error": str(exc)}


class AudioHub:
    """One physical input shared by listeners; the last departure releases it."""

    def __init__(self):
        self.lock = asyncio.Lock()
        self.stream = None
        self.device = None
        self.subscribers = ()
        self.sample_rate = 16000
        self.channels = 1
        self.device_name = ""

    def publish(self, data, frames, timing, status):
        # PortAudio's thread never waits for network clients. Drop old audio.
        if self.channels > 1:
            values = np.frombuffer(data, dtype=np.int16).reshape(-1, self.channels)
            # Use the strongest input channel: averaging a microphone array can
            # cancel out-of-phase channels or dilute a single active channel.
            energy = np.sum(values.astype(np.float32) ** 2, axis=0)
            payload = values[:, int(np.argmax(energy))].copy().tobytes()
        else:
            payload = bytes(data)
        for subscriber in self.subscribers:
            try:
                subscriber.put_nowait(payload)
            except queue.Full:
                try:
                    subscriber.get_nowait()
                except queue.Empty:
                    pass
                try:
                    subscriber.put_nowait(payload)
                except queue.Full:
                    pass

    def open(self, device):
        import sounddevice as sd

        info = sd.query_devices(device, "input")
        native_rate = int(info["default_samplerate"])
        channels = min(2, int(info["max_input_channels"]))
        attempts = dict.fromkeys(
            [(native_rate, channels), (native_rate, 1), (16000, channels), (16000, 1)]
        )
        last_error = None
        for rate, count in attempts:
            stream = None
            try:
                sd.check_input_settings(
                    device=device, channels=count, dtype="int16", samplerate=rate
                )
                self.channels = count
                stream = sd.RawInputStream(
                    device=device,
                    samplerate=rate,
                    channels=count,
                    dtype="int16",
                    blocksize=rate // 50,
                    callback=self.publish,
                )
                stream.start()
            except Exception as exc:
                if stream is not None:
                    stream.close()
                last_error = exc
                continue
            self.stream, self.device, self.sample_rate = stream, device, rate
            self.device_name = info["name"]
            return
        raise RuntimeError(
            f"Cannot open the microphone. Check Windows microphone permissions and input device settings. {last_error}"
        )

    def resolve_device(self, device):
        if device is not None:
            return device
        options = input_devices()
        if not options["available"]:
            raise ValueError(
                "No Windows microphone is available. Check its connection and Windows Sound input settings."
            )
        return options["default_device"]

    async def subscribe(self, device=None):
        async with self.lock:
            device = await asyncio.to_thread(self.resolve_device, device)
            if self.stream is not None and device != self.device:
                raise ValueError(
                    "Another viewer is using a different server microphone. Select the same input or wait until they stop listening."
                )
            if self.stream is None:
                await asyncio.to_thread(self.open, device)
            subscriber = queue.Queue(maxsize=5)
            self.subscribers += (subscriber,)
            return subscriber, self.sample_rate

    async def unsubscribe(self, subscriber):
        async with self.lock:
            self.subscribers = tuple(item for item in self.subscribers if item is not subscriber)
            if not self.subscribers:
                await self.close_stream()

    async def close_stream(self):
        stream, self.stream = self.stream, None
        if stream is not None:
            try:
                await asyncio.to_thread(stream.stop)
            finally:
                await asyncio.to_thread(stream.close)

    async def close(self):
        async with self.lock:
            self.subscribers = ()
            await self.close_stream()
