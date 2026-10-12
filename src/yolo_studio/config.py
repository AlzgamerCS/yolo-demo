"""Validated per-browser configuration and legacy feature mappings."""
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from .capture import DEFAULT_PHONE, network_url

LEGACY_FEATURES = {'raw': [], 'detect': ['detect'], 'segment': ['detect', 'segment'], 'pose': ['pose'], 'all': ['detect', 'segment', 'pose']}

class Config(BaseModel):
    source: Literal['laptop', 'browser', 'phone', 'url'] = 'laptop'
    camera: int = Field(default=0, ge=0, le=20)
    url: str = Field(default=DEFAULT_PHONE, max_length=2048)
    mode: Literal['raw', 'detect', 'segment', 'pose', 'all', 'custom'] = 'all'
    features: list[Literal['detect', 'segment', 'pose']] | None = Field(default=None, max_length=3)
    share_with_operator: bool = False
    size: Literal['n', 's', 'm', 'l', 'x'] = 'n'
    device: str = Field(default='auto', max_length=24)
    imgsz: Literal[320, 480, 640, 960, 1280] = 480
    confidence: float = Field(default=0.35, ge=0, le=1)
    boxes: bool = True
    width: int = Field(default=1280, ge=160, le=3840)
    height: int = Field(default=720, ge=120, le=2160)
    preview_width: Literal[640, 960, 1280, 1920] = 960
    quality: int = Field(default=75, ge=35, le=95)
    max_fps: int = Field(default=20, ge=1, le=60)

    @model_validator(mode='after')
    def validate_stream(self):
        if self.features is None:
            if self.mode == 'custom':
                raise ValueError('Custom mode requires a features checklist.')
            self.features = LEGACY_FEATURES[self.mode].copy()
        self.features = list(dict.fromkeys(self.features))
        selected = set(self.features)
        self.mode = 'raw' if not selected else 'all' if selected == {'detect', 'segment', 'pose'} else next(iter(selected)) if len(selected) == 1 else 'custom'
        if self.source not in ('laptop', 'browser'):
            if not network_url(self.url.strip(), phone=self.source == 'phone'):
                raise ValueError('Use a direct HTTP/HTTPS/RTSP video stream URL.')
        return self
