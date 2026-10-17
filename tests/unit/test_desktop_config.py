"""Configuration precedence and validation without camera/model initialization."""
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from yolo_studio.cli.desktop import build_parser
from yolo_studio.desktop_config import parse_desktop_args


class DesktopConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'desktop.toml'

    def settings(self, contents, *flags):
        self.path.write_text(contents, encoding='utf-8')
        return parse_desktop_args(build_parser(), ['--config', str(self.path), *flags])

    def test_settings_and_cli_precedence(self):
        args = self.settings('[desktop]\nmode="pose"\nsize="s"\ndevice="gpu"\nconfidence=0.6\nfullscreen=true\nno_boxes=true\n',
                             '--device', 'cpu', '--windowed', '--boxes')
        self.assertEqual((args.mode, args.size, args.device, args.confidence), ('pose', 's', 'cpu', .6))
        self.assertFalse(args.fullscreen)
        self.assertFalse(args.no_boxes)

    def test_source_flags_replace_configured_source(self):
        document = '[desktop]\nphone="http://phone:8080"\n'
        args = self.settings(document, '--source', 'other.mp4')
        self.assertEqual(args.source, 'other.mp4')
        self.assertIsNone(args.phone)
        args = self.settings(document, '--webcam', '--camera', '2')
        self.assertEqual(args.camera, 2)
        self.assertIsNone(args.phone)
        self.assertIsNone(args.source)
        args = self.settings('[desktop]\nsource="clip.mp4"', '--phone')
        self.assertIsNone(args.source)
        self.assertTrue(args.phone.startswith('http'))

    def test_file_paths_are_relative_to_config(self):
        args = self.settings('[desktop]\nmode="detect"\nmodel="weights.pt"\nsource="clip.mp4"\n')
        self.assertEqual(Path(args.model), self.path.parent / 'weights.pt')
        self.assertEqual(Path(args.source), self.path.parent / 'clip.mp4')

    def test_default_file_and_opt_out(self):
        self.path.write_text('[desktop]\nmode="pose"\n', encoding='utf-8')
        with patch('yolo_studio.desktop_config.DEFAULT_CONFIG', self.path):
            self.assertEqual(parse_desktop_args(build_parser(), []).mode, 'pose')
            self.assertEqual(parse_desktop_args(build_parser(), ['--no-config']).mode, 'all')
        with patch('yolo_studio.desktop_config.DEFAULT_CONFIG', self.path.parent / 'missing.toml'):
            self.assertEqual(parse_desktop_args(build_parser(), []).device, 'auto')

    def test_bad_settings_fail_before_opening_camera(self):
        for document in ['[desktop]\nsize="z"', '[desktop]\nimgsz="480"',
                         '[desktop]\nfullscreen="yes"', '[desktop]\ncamera=true',
                         '[desktop]\nconfidence=2', '[desktop]\nwidth=0',
                         '[desktop]\nunknown=1', '[desktop]\ncheck=true',
                         '[desktop]\nsource="x"\nphone="http://phone"',
                         '[desktop]\nmodel="weights.pt"', '[web]\ndevice="cpu"',
                         '[desktop\nmode="pose"']:
            with self.subTest(document=document), redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as error:
                    self.settings(document)
                self.assertEqual(error.exception.code, 2)

    def test_explicit_missing_file_is_an_error(self):
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            parse_desktop_args(build_parser(), ['--config', str(self.path)])


if __name__ == '__main__':
    unittest.main()
