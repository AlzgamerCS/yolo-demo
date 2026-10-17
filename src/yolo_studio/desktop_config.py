"""Validated TOML defaults for the standalone desktop interface."""
import argparse
from pathlib import Path
import tomllib
from .capture import network_url
from .paths import PROJECT_ROOT

DEFAULT_CONFIG = PROJECT_ROOT / 'config' / 'desktop.toml'
CONTROL_OPTIONS = {'help', 'config', 'no_config', 'check', 'list_devices', 'webcam'}


def read_settings(path, parser):
    with path.open('rb') as handle:
        document = tomllib.load(handle)
    if set(document) != {'desktop'} or not isinstance(document['desktop'], dict):
        raise ValueError('Use one [desktop] table containing desktop settings.')
    actions = {}
    for action in parser._actions:
        if action.dest not in CONTROL_OPTIONS:
            actions.setdefault(action.dest, action)
    settings = document['desktop']
    for key, value in settings.items():
        if key not in actions:
            raise ValueError(f'Unknown desktop setting: {key}')
        action = actions[key]
        expected = bool if isinstance(action.default, bool) else action.type or str
        valid = (type(value) in (int, float) if expected is float else type(value) is expected)
        if not valid:
            raise ValueError(f'{key} must be {expected.__name__}, received {type(value).__name__}.')
        if action.choices and value not in action.choices:
            raise ValueError(f'{key} must be one of: {", ".join(action.choices)}')
        if isinstance(value, str) and not value.strip():
            raise ValueError(f'{key} cannot be empty; omit the setting to use its default.')
    if settings.get('source') and settings.get('phone'):
        raise ValueError('Configure either source or phone, not both.')
    # File paths belong to the configuration, not the terminal's working directory.
    for key in ('source', 'model'):
        value = settings.get(key)
        if value and not network_url(value):
            settings[key] = str((path.parent / Path(value).expanduser()).resolve())
    return settings


def parse_desktop_args(parser, argv=None):
    # First parse identifies an alternate file and explicit source overrides.
    cli = parser.parse_args(argv)
    path = Path(cli.config).expanduser().resolve() if cli.config else DEFAULT_CONFIG
    settings = {}
    if not cli.no_config and (cli.config or path.is_file()):
        try:
            settings = read_settings(path, parser)
        except (OSError, ValueError) as exc:
            parser.error(f'Cannot load desktop config {path}: {exc}')
    if cli.phone is not None:
        settings.pop('source', None)
    if cli.source is not None:
        settings.pop('phone', None)
    if cli.webcam:
        settings.pop('source', None)
        settings.pop('phone', None)
    args = parser.parse_args(argv, namespace=argparse.Namespace(**settings))
    if not 0 <= args.confidence <= 1 or min(args.imgsz, args.width, args.height, args.window_width, args.window_height) <= 0:
        parser.error('confidence must be between 0 and 1; all dimensions must be positive')
    if args.camera < 0:
        parser.error('camera must be a non-negative index')
    if args.model and args.mode == 'all':
        parser.error('--model requires --mode detect, segment, or pose')
    return args
