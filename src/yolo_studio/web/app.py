"""Application assembly; transport behavior lives in the routers."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ..paths import STATIC_DIR
from .lifecycle import lifespan
from .middleware import local_controls
from .routes import audio, controls, operator, pages, streaming


def create_app():
    app = FastAPI(title="YOLO Studio", lifespan=lifespan)
    app.middleware("http")(local_controls)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    for router in (pages.router, controls.router, operator.router, streaming.router, audio.router):
        app.include_router(router)
    return app


app = create_app()
