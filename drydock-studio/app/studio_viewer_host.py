from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit, unquote
import urllib.request
import mimetypes

ROOT = Path(__file__).resolve().parent
DIST = ROOT.parents[1] / '3D Gen Studio/resources/app/dist'

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        route = unquote(urlsplit(self.path).path)
        if route == '/health':
            return self.send(b'jackdaw-studio-viewer', 'text/plain')
        if route.startswith('/api/'):
            try:
                with urllib.request.urlopen('http://127.0.0.1:3001' + self.path, timeout=10) as r:
                    return self.send(r.read(), r.headers.get('Content-Type', 'application/json'))
            except Exception:
                return self.send(b'{"error":"Studio backend unavailable"}', 'application/json', 503)
        if route.startswith('/ship-preview/'):
            base, rel = ROOT / 'user-data/ship-preview', route[len('/ship-preview/'):]
        elif route.startswith('/vendor/'):
            base, rel = ROOT / 'high-detail-viewer', route[1:]
        elif route == '/finish-editor.js':
            base, rel = ROOT / 'high-detail-viewer', 'finish-editor.js'
        elif route in ['/studio-bridge.js', '/studio-boot.glb']:
            base, rel = ROOT, route[1:]
        else:
            base, rel = DIST, route.lstrip('/')
        file = (base / rel).resolve()
        if not file.is_relative_to(base.resolve()):
            return self.send(b'Forbidden', 'text/plain', 403)
        if route in ['/', '/mesh-editor']:
            html = (DIST / 'index.html').read_text(encoding='utf-8')
            html = html.replace('<head>', '<head><script type="importmap">{"imports":{"three":"/vendor/three/three.module.js"}}</script>')
            html = html.replace('</body>', (ROOT / 'studio-overlay.html').read_text(encoding='utf-8') + '</body>')
            return self.send(html.encode(), 'text/html')
        if not file.is_file():
            return self.send(b'Not found', 'text/plain', 404)
        if file.name == 'index-9sLrGF00.js':
            js = file.read_text(encoding='utf-8')
            needle = 'function Sj({store:e,children:t,onCreated:n,rootElement:r}){return'
            assert js.count(needle) == 1
            js = js.replace(needle, 'function Sj({store:e,children:t,onCreated:n,rootElement:r}){window.__jackdawStudioStore=e;return')
            return self.send(js.encode(), 'text/javascript')
        return self.send(file.read_bytes(), mimetypes.guess_type(file.name)[0] or 'application/octet-stream')

    def send(self, data, kind, status=200):
        self.send_response(status)
        if kind.startswith('text/') or kind == 'application/javascript':
            kind += '; charset=utf-8'
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

ThreadingHTTPServer(('127.0.0.1', 8767), Handler).serve_forever()
