"""Local-only access to consenting clients and their frames."""
from typing import Literal
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from fastapi.responses import FileResponse
from ...paths import TEMPLATES_DIR

router = APIRouter()

def require_operator(request):
    if request.url.hostname not in ('localhost', '127.0.0.1', '::1') or request.client.host not in ('127.0.0.1', '::1'):
        raise HTTPException(status_code=403, detail='The operator monitor is available only on the server laptop through localhost.')


@router.get('/monitor')
def monitor(request: Request):
    require_operator(request)
    return FileResponse(TEMPLATES_DIR / 'monitor.html')


@router.get('/api/operator/sessions')
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


@router.get('/api/operator/frame/{identifier}')
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
