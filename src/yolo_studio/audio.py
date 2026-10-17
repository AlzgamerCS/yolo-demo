"""Shared, on-demand server microphone capture with bounded listener buffers."""
import asyncio
import queue


def input_devices():
    """Enumerate inputs without opening or recording the microphone."""
    try:
        import sounddevice as sd
        devices = [
            {'value': str(index), 'label': info['name']}
            for index, info in enumerate(sd.query_devices())
            if info['max_input_channels'] > 0
        ]
        return {'available': bool(devices), 'devices': devices, 'error': ''}
    except Exception as exc:
        return {'available': False, 'devices': [], 'error': str(exc)}


class AudioHub:
    """One physical input shared by listeners; the last departure releases it."""

    def __init__(self):
        self.lock = asyncio.Lock()
        self.stream = None
        self.device = None
        self.subscribers = ()
        self.sample_rate = 16000

    def publish(self, data, frames, timing, status):
        # PortAudio's thread never waits for network clients. Drop old audio.
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
        rate = 16000
        try:
            sd.check_input_settings(device=device, channels=1, dtype='int16', samplerate=rate)
        except sd.PortAudioError:
            rate = int(sd.query_devices(device, 'input')['default_samplerate'])
        stream = sd.RawInputStream(device=device, samplerate=rate, channels=1,
                                   dtype='int16', blocksize=rate // 50,
                                   callback=self.publish)
        try:
            stream.start()
        except BaseException:
            stream.close()
            raise
        self.stream, self.device, self.sample_rate = stream, device, rate

    async def subscribe(self, device=None):
        async with self.lock:
            if self.stream is not None and device != self.device:
                raise ValueError('Another viewer is using a different server microphone. Select the same input or wait until they stop listening.')
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
