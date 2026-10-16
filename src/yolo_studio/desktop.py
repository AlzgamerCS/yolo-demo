"""Compatibility entry point; implementation is in cli.desktop."""
from .cli.desktop import build_parser, main, run

if __name__ == "__main__":
    run()
