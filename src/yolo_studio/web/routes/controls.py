"""Runtime options and per-session controls."""

import torch
from fastapi import APIRouter, HTTPException, Request

from ...capture import DEFAULT_PHONE
from ...config import ClientSharing, Config

router = APIRouter()


@router.get("/api/options")
def options():
    devices = [
        {"value": "auto", "label": "Auto · GPU when available"},
        {"value": "cpu", "label": "CPU"},
    ]
    for index in range(torch.cuda.device_count()):
        devices.append(
            {"value": str(index), "label": f"GPU {index} · {torch.cuda.get_device_name(index)}"}
        )
    if not torch.cuda.is_available():
        devices.append(
            {"value": "gpu", "label": "GPU · unavailable in this build", "disabled": True}
        )
    return {
        "devices": devices,
        "gpu_available": torch.cuda.is_available(),
        "default_phone": DEFAULT_PHONE,
    }


@router.get("/api/status")
def status(request: Request):
    return request.state.engine.status()


@router.post("/api/config")
def configure(config: Config, request: Request):
    try:
        request.state.engine.apply(config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return request.state.engine.status()


@router.post("/api/stop")
def stop(request: Request):
    request.state.engine.stop()
    return {"ok": True}


@router.post("/api/sharing")
def sharing(settings: ClientSharing, request: Request):
    engine = request.state.engine
    with engine.condition:
        engine.config = engine.config.model_copy(update=settings.model_dump())
        if not settings.share_with_operator:
            engine.raw_jpeg = None
        if not settings.share_with_operator or not settings.share_audio:
            engine.client_audio.clear()
    return engine.status()
