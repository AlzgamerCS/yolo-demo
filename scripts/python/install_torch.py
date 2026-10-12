"""Install official PyTorch wheels using the primary host for wheel downloads."""
import argparse
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import urlopen


class WheelLinks(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base = base
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != 'a':
            return
        href = dict(attrs).get('href')
        if not href:
            return
        parsed = urlsplit(urljoin(self.base, href))
        if parsed.hostname not in ('download.pytorch.org', 'download-r2.pytorch.org'):
            return
        # Both official hosts serve the same wheel paths. The primary host works
        # on networks where the newer R2 download hostname does not resolve.
        self.links.append(urlunsplit(('https', 'download.pytorch.org', parsed.path, parsed.query, parsed.fragment)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', default='cpu')
    args = parser.parse_args()
    if args.index != 'cpu' and not re.fullmatch(r'cu\d+', args.index):
        parser.error('Index must be cpu or cu followed by digits.')
    with tempfile.TemporaryDirectory(prefix='yolo-torch-index-') as temporary:
        index_root = Path(temporary)
        for package in ('torch', 'torchvision'):
            url = f'https://download.pytorch.org/whl/{args.index}/{package}/'
            with urlopen(url, timeout=60) as response:
                links = WheelLinks(url)
                links.feed(response.read().decode('utf-8'))
            if not links.links:
                raise RuntimeError(f'No official wheel links found at {url}')
            directory = index_root / package
            directory.mkdir()
            html = '\n'.join(f'<a href="{escape(link, quote=True)}">wheel</a>' for link in links.links)
            (directory / 'index.html').write_text(html, encoding='utf-8')
        command = ['uv', 'pip', 'install', '--python', sys.executable,
                   '--reinstall-package', 'torch', '--reinstall-package', 'torchvision',
                   '--index', index_root.as_uri(), '--default-index', 'https://pypi.org/simple',
                   'torch', 'torchvision']
        subprocess.run(command, check=True)


if __name__ == '__main__':
    main()
