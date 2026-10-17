"""Latest-frame HTTP fallback and WebSocket transport."""

import asyncio

import cv2
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

router = APIRouter()


@router.get("/api/frame")
def frame(request: Request, after: int = -1):
    engine = request.state.engine
    with engine.condition:
        if engine.jpeg is None or engine.frame_id <= after:
            return Response(status_code=204)
        return Response(
            engine.jpeg, media_type="image/jpeg", headers={"X-Frame-Id": str(engine.frame_id)}
        )


@router.post("/api/browser-frame")
async def browser_frame(request: Request, generation: int):
    if request.headers.get("content-type", "").split(";")[0] != "image/jpeg":
        raise HTTPException(status_code=415, detail="Send a JPEG frame.")
    # Limit the upload before decoding; no video is written to disk.
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > 2_000_000:
            raise HTTPException(
                status_code=413,
                detail="Camera frame is too large. Reduce upload resolution/quality.",
            )
    import numpy as np

    frame = await asyncio.to_thread(
        cv2.imdecode, np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR
    )
    if frame is None or max(frame.shape[:2]) > 4096:
        raise HTTPException(status_code=400, detail="Invalid JPEG camera frame.")
    accepted = request.state.engine.upload(frame, generation, payload)
    return Response(status_code=204 if accepted else 409)


@router.websocket("/api/live")
async def live(socket: WebSocket):
    expected_origin = (
        str(socket.url)
        .split("/api/live")[0]
        .replace("wss://", "https://")
        .replace("ws://", "http://")
    )
    if socket.headers.get("origin") != expected_origin:
        await socket.close(code=1008)
        return
    registry = socket.app.state.sessions
    identifier = socket.cookies.get("yolo_session")
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
            generation = int.from_bytes(payload[:4], "big")
            frame = await asyncio.to_thread(
                cv2.imdecode, np.frombuffer(payload[4:], np.uint8), cv2.IMREAD_COLOR
            )
            if frame is not None and max(frame.shape[:2]) <= 4096:
                engine.upload(frame, generation, payload[4:])

    async def send():
        last_id = -1
        while True:
            with engine.condition:
                jpeg, identifier, generation = engine.jpeg, engine.frame_id, engine.generation
            if jpeg is not None and identifier != last_id:
                # Prefix ID + generation so clients can discard stale sessions.
                await socket.send_bytes(
                    identifier.to_bytes(4, "big") + generation.to_bytes(4, "big") + jpeg
                )
                last_id = identifier
            await asyncio.sleep(0.005)

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
