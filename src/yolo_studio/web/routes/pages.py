"""Browser dashboard entry page."""

from fastapi import APIRouter
from fastapi.responses import FileResponse

from ...paths import TEMPLATES_DIR

router = APIRouter()


@router.get("/")
def home():
    return FileResponse(TEMPLATES_DIR / "index.html")
