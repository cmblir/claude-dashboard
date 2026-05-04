// Tiny static file server used by phase 3+ acceptance tests.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
};

export function startStaticServer(rootDir, port = 0) {
  const root = path.resolve(rootDir);
  const server = http.createServer((req, res) => {
    let urlPath = (req.url || '/').split('?')[0];
    if (urlPath === '/') urlPath = '/index.html';
    const file = path.normalize(path.join(root, urlPath));
    if (!file.startsWith(root)) { res.statusCode = 403; res.end('forbidden'); return; }
    if (!fs.existsSync(file) || !fs.statSync(file).isFile()) { res.statusCode = 404; res.end('not found'); return; }
    res.setHeader('content-type', MIME[path.extname(file)] || 'application/octet-stream');
    res.setHeader('cache-control', 'no-store');
    res.end(fs.readFileSync(file));
  });
  return new Promise(resolve => {
    server.listen(port, '127.0.0.1', () => {
      const addr = server.address();
      const realPort = typeof addr === 'object' && addr ? addr.port : port;
      resolve({ server, port: realPort, url: `http://127.0.0.1:${realPort}` });
    });
  });
}
