"""Browser microphone upload and local-only operator audio relay."""

import asyncio
import json
import time
import uuid
from contextlib import suppress

import anyio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError

from .operator import require_operator

router = APIRouter()


class AudioFormat(BaseModel):
    sample_rate: int = Field(ge=8000, le=96000)


def same_origin(socket):
    return socket.headers.get("origin") == str(socket.url).split("/api/")[0].replace(
        "wss://", "https://"
    ).replace("ws://", "http://")


def allowed(engine, generation):
    return (
        not engine.closed
        and engine.active
        and engine.config.source == "browser"
        and engine.config.share_with_operator
        and engine.config.share_audio
        and engine.generation == generation
        and engine.phase != "error"
    )


@router.websocket("/api/client-audio")
async def upload(socket: WebSocket, generation: int):
    registry = socket.app.state.sessions
    with registry.lock:
        entry = registry.items.get(socket.cookies.get("yolo_session"))
    if not same_origin(socket) or entry is None:
        await socket.close(code=1008)
        return
    engine = entry[0]
    with engine.condition:
        permitted = allowed(engine, generation)
    if not permitted:
        await socket.close(code=1008)
        return
    await socket.accept()
    owner = uuid.uuid4().hex
    try:
        header = await asyncio.wait_for(socket.receive_text(), 5)
        if len(header) > 256:
            await socket.close(code=1009)
            return
        metadata = AudioFormat.model_validate(json.loads(header))
        with engine.condition:
            permitted = allowed(engine, generation)
            if permitted:
                engine.client_audio.clear()
                engine.client_audio.owner = owner
                engine.client_audio.sample_rate = metadata.sample_rate
        if not permitted:
            await socket.close(code=1008)
            return
        while True:
            payload = await asyncio.wait_for(socket.receive_bytes(), 10)
            if not payload or len(payload) % 2 or len(payload) > metadata.sample_rate // 5:
                await socket.close(code=1009)
                return
            with engine.condition:
                permitted = allowed(engine, generation) and engine.client_audio.owner == owner
                if permitted:
                    engine.client_audio.push(payload)
            if not permitted:
                await socket.close(code=1000)
                return
    except (TimeoutError, WebSocketDisconnect):
        pass
    except (ValueError, ValidationError, RuntimeError, KeyError, TypeError):
        with suppress(RuntimeError):
            await socket.close(code=1008)
    finally:
        with engine.condition:
            if engine.client_audio.owner == owner:
                engine.client_audio.clear()


@router.websocket("/api/operator/audio/{identifier}")
async def listen(identifier: str, socket: WebSocket):
    try:
        require_operator(socket)
    except HTTPException:
        await socket.close(code=1008)
        return
    registry = socket.app.state.sessions
    with registry.lock:
        engine = next(
            (entry[0] for entry in registry.items.values() if entry[0].public_id == identifier),
            None,
        )
    if engine is None or not same_origin(socket):
        await socket.close(code=1008)
        return
    with engine.condition:
        generation = engine.generation
        permitted = allowed(engine, generation)
    if not permitted:
        await socket.close(code=1008)
        return
    await socket.accept()

    async def send():
        last_sequence, last_rate = -1, None
        while True:
            with engine.condition:
                permitted = allowed(engine, generation)
                rate = engine.client_audio.sample_rate
                packets = [
                    item
                    for item in engine.client_audio.packets
                    if item[0] > last_sequence and time.monotonic() - item[1] < 0.5
                ]
            if not permitted:
                await socket.close(code=1000)
                return
            if rate and rate != last_rate:
                await socket.send_json({"sample_rate": rate})
                last_rate = rate
            for sequence, _, payload in packets:
                await asyncio.wait_for(socket.send_bytes(payload), 2)
                last_sequence = sequence
            await asyncio.sleep(0.005)

    async def receive():
        while (await socket.receive())["type"] != "websocket.disconnect":
            pass

    tasks = [asyncio.create_task(send()), asyncio.create_task(receive())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except (TimeoutError, WebSocketDisconnect, RuntimeError):
        pass
    finally:
        with anyio.CancelScope(shield=True):
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
