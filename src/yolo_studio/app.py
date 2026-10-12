"""FastAPI routes, WebSocket streaming, and local operator access."""
import asyncio
from contextlib import asynccontextmanager
from typing import Literal
import cv2
import torch
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from .config import Config
from .capture import DEFAULT_PHONE
from .engine import Sessions
from .paths import FRONTEND_DIR

@asynccontextmanager
async def lifespan(app):
    app.state.sessions = Sessions()
    async def cleanup():
        while True:
            await asyncio.sleep(15)
            await asyncio.to_thread(app.state.sessions.prune)
    task = asyncio.create_task(cleanup())
    yield
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.to_thread(app.state.sessions.prune, True)


app = FastAPI(title='YOLO Studio', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=FRONTEND_DIR), name='static')


@app.middleware('http')
async def local_controls(request: Request, call_next):
    # No cross-origin control requests; the server binds to loopback by default.
    origin = request.headers.get('origin')
    if request.method == 'POST' and origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
        return JSONResponse({'detail': 'Open the dashboard on the same server to control the camera.'}, status_code=403)
    try:
        identifier, engine = request.app.state.sessions.get(request.cookies.get('yolo_session'))
    except HTTPException as exc:
        return JSONResponse({'detail': exc.detail}, status_code=exc.status_code)
    request.state.engine = engine
    response = await call_next(request)
    if request.cookies.get('yolo_session') != identifier:
        response.set_cookie('yolo_session', identifier, httponly=True, samesite='strict', secure=request.url.scheme == 'https')
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/')
def home():
    return FileResponse(FRONTEND_DIR / 'index.html')


def require_operator(request):
    if request.url.hostname not in ('localhost', '127.0.0.1', '::1') or request.client.host not in ('127.0.0.1', '::1'):
        raise HTTPException(status_code=403, detail='The operator monitor is available only on the server laptop through localhost.')


@app.get('/monitor')
def monitor(request: Request):
    require_operator(request)
    return FileResponse(FRONTEND_DIR / 'monitor.html')


@app.get('/api/operator/sessions')
def operator_sessions(request: Request):
    require_operator(request)
    with request.app.state.sessions.lock:
        engines = [entry[0] for entry in request.app.state.sessions.items.values()]
    sessions = []
    for engine in engines:
        with engine.condition:
            if engine.config.source == 'browser' and engine.config.share_with_operator and engine.active:
                sessions.append({'id': engine.public_id, 'label': 'Client ' + engine.public_id[:8],
                                 'phase': engine.phase, 'features': engine.config.features,
                                 'metrics': dict(engine.metrics), 'raw_ready': engine.raw_jpeg is not None})
    return {'sessions': sessions}


@app.get('/api/operator/frame/{identifier}')
def operator_frame(identifier: str, request: Request, kind: Literal['raw', 'processed'] = 'raw', after: int = -1):
    require_operator(request)
    with request.app.state.sessions.lock:
        engine = next((entry[0] for entry in request.app.state.sessions.items.values() if entry[0].public_id == identifier), None)
    if engine is None:
        raise HTTPException(status_code=404, detail='Client session ended.')
    with engine.condition:
        if not engine.active or engine.config.source != 'browser' or not engine.config.share_with_operator:
            raise HTTPException(status_code=403, detail='This client has not enabled sharing or has stopped the camera.')
        jpeg, frame_id = (engine.raw_jpeg, engine.raw_frame_id) if kind == 'raw' else (engine.jpeg, engine.frame_id)
        if jpeg is None or frame_id <= after:
            return Response(status_code=204)
        return Response(jpeg, media_type='image/jpeg', headers={'X-Frame-Id': str(frame_id)})


@app.get('/api/options')
def options():
    devices = [{'value': 'auto', 'label': 'Auto · GPU when available'}, {'value': 'cpu', 'label': 'CPU'}]
    for index in range(torch.cuda.device_count()):
        devices.append({'value': str(index), 'label': f'GPU {index} · {torch.cuda.get_device_name(index)}'})
    if not torch.cuda.is_available():
        devices.append({'value': 'gpu', 'label': 'GPU · unavailable in this build', 'disabled': True})
    return {'devices': devices, 'gpu_available': torch.cuda.is_available(), 'default_phone': DEFAULT_PHONE}


@app.get('/api/status')
def status(request: Request):
    return request.state.engine.status()


@app.post('/api/config')
def configure(config: Config, request: Request):
    try:
        request.state.engine.apply(config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return request.state.engine.status()


@app.post('/api/stop')
def stop(request: Request):
    request.state.engine.stop()
    return {'ok': True}


@app.get('/api/frame')
def frame(request: Request, after: int = -1):
    engine = request.state.engine
    with engine.condition:
        if engine.jpeg is None or engine.frame_id <= after:
            return Response(status_code=204)
        return Response(engine.jpeg, media_type='image/jpeg', headers={'X-Frame-Id': str(engine.frame_id)})


@app.post('/api/browser-frame')
async def browser_frame(request: Request, generation: int):
    if request.headers.get('content-type', '').split(';')[0] != 'image/jpeg':
        raise HTTPException(status_code=415, detail='Send a JPEG frame.')
    # Limit the upload before decoding; no video is written to disk.
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > 2_000_000:
            raise HTTPException(status_code=413, detail='Camera frame is too large. Reduce upload resolution/quality.')
    import numpy as np
    frame = await asyncio.to_thread(cv2.imdecode, np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None or max(frame.shape[:2]) > 4096:
        raise HTTPException(status_code=400, detail='Invalid JPEG camera frame.')
    accepted = request.state.engine.upload(frame, generation, payload)
    return Response(status_code=204 if accepted else 409)


@app.websocket('/api/live')
async def live(socket: WebSocket):
    expected_origin = str(socket.url).split('/api/live')[0].replace('wss://', 'https://').replace('ws://', 'http://')
    if socket.headers.get('origin') != expected_origin:
        await socket.close(code=1008)
        return
    registry = socket.app.state.sessions
    identifier = socket.cookies.get('yolo_session')
    with registry.lock:
        entry = registry.items.get(identifier)
    if entry is None:
        await socket.close(code=1008)
        return
    engine = entry[0]
    await socket.accept()
    latest_upload = None
    wake = asyncio.Event()

    async def receive():
        nonlocal latest_upload
        while True:
            payload = await socket.receive_bytes()
            # Four-byte generation prefix binds each JPEG to its source/config.
            if not 4 < len(payload) <= 2_000_004:
                await socket.close(code=1009)
                return
            latest_upload = payload
            wake.set()

    async def decode():
        nonlocal latest_upload
        import numpy as np
        while True:
            await wake.wait()
            payload, latest_upload = latest_upload, None
            wake.clear()
            generation = int.from_bytes(payload[:4], 'big')
            frame = await asyncio.to_thread(cv2.imdecode, np.frombuffer(payload[4:], np.uint8), cv2.IMREAD_COLOR)
            if frame is not None and max(frame.shape[:2]) <= 4096:
                engine.upload(frame, generation, payload[4:])

    async def send():
        last_id = -1
        while True:
            with engine.condition:
                jpeg, identifier, generation = engine.jpeg, engine.frame_id, engine.generation
            if jpeg is not None and identifier != last_id:
                # Prefix ID + generation so clients can discard stale sessions.
                await socket.send_bytes(identifier.to_bytes(4, 'big') + generation.to_bytes(4, 'big') + jpeg)
                last_id = identifier
            await asyncio.sleep(.005)

    tasks = [asyncio.create_task(function()) for function in (receive, decode, send)]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
