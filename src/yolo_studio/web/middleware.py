"""Same-origin controls and browser session cookies."""

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


async def local_controls(request: Request, call_next):
    # No cross-origin control requests; the server binds to loopback by default.
    origin = request.headers.get("origin")
    if (
        request.method == "POST"
        and origin
        and origin.rstrip("/") != str(request.base_url).rstrip("/")
    ):
        return JSONResponse(
            {"detail": "Open the dashboard on the same server to control the camera."},
            status_code=403,
        )
    try:
        identifier, engine = request.app.state.sessions.get(request.cookies.get("yolo_session"))
    except HTTPException as exc:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    request.state.engine = engine
    response = await call_next(request)
    if request.cookies.get("yolo_session") != identifier:
        response.set_cookie(
            "yolo_session",
            identifier,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
        )
    response.headers["Cache-Control"] = "no-store"
    return response
