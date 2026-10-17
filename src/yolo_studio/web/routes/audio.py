"""Explicit listener access to the microphone paired with a server camera."""
import asyncio
import queue
import anyio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ...audio import input_devices

router = APIRouter()


@router.get('/api/audio/devices')
async def devices():
    return await asyncio.to_thread(input_devices)


@router.websocket('/api/audio')
async def listen(socket: WebSocket, device: int | None = None):
    expected = str(socket.url).split('/api/audio')[0].replace('wss://', 'https://').replace('ws://', 'http://')
    registry = socket.app.state.sessions
    with registry.lock:
        entry = registry.items.get(socket.cookies.get('yolo_session'))
    if socket.headers.get('origin') != expected or entry is None:
        await socket.close(code=1008)
        return
    engine = entry[0]
    with engine.condition:
        generation = engine.generation

    def allowed():
        with engine.condition:
            return (engine.active and not engine.closed and engine.phase == 'running'
                    and engine.config.source == 'laptop' and engine.generation == generation)

    if not allowed():
        await socket.close(code=1008)
        return
    await socket.accept()
    hub = socket.app.state.audio
    subscriber = None

    async def send():
        while allowed():
            try:
                payload = await asyncio.to_thread(subscriber.get, True, .2)
            except queue.Empty:
                if hub.stream is None or not hub.stream.active:
                    raise RuntimeError('Server microphone stopped. Check its connection and Windows microphone permissions.')
                continue
            if not allowed():
                break
            await asyncio.wait_for(socket.send_bytes(payload), timeout=2)
        await socket.close(code=1000)

    async def receive():
        # Reading also detects a silent listener disconnect, releasing capture.
        while True:
            message = await socket.receive()
            if message['type'] == 'websocket.disconnect':
                return

    tasks = []
    try:
        subscriber, rate = await hub.subscribe(device)
        await socket.send_json({'sample_rate': rate, 'channels': 1, 'format': 's16le'})
        tasks = [asyncio.create_task(send()), asyncio.create_task(receive())]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except Exception as exc:
        try:
            await socket.send_json({'error': f'Audio unavailable: {exc}'})
            await socket.close(code=1011)
        except (WebSocketDisconnect, RuntimeError):
            pass
    finally:
        # ASGI can cancel a disconnected request while its cleanup is awaiting.
        with anyio.CancelScope(shield=True):
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if subscriber is not None:
                await hub.unsubscribe(subscriber)
