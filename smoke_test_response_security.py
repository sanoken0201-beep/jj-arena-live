"""Exercise actual final response boundaries, including early exits and HTTP 500."""
import os
import tempfile
from fastapi.testclient import TestClient
from fastapi import HTTPException
from starlette.responses import RedirectResponse, StreamingResponse


def main():
    os.environ.pop('DATABASE_URL', None)
    os.environ['JJ_DB_PATH'] = tempfile.mkdtemp(prefix='jj-response-security-') + '/test.db'
    os.environ['RENDER'] = '1'
    os.environ['JJ_ENABLE_DEMO_MEMBER'] = '0'
    import app as production
    from response_security import HEADERS
    app = production.app

    async def missing():
        raise HTTPException(404, 'test missing')
    async def failed():
        raise RuntimeError('injected test failure')
    async def redirect():
        return RedirectResponse('/')
    async def stream():
        async def chunks():
            yield b'first'
            yield b'second'
        return StreamingResponse(chunks())
    # Insert before SPA fallback. These routes exist only in this isolated process.
    from starlette.routing import Route
    for path, fn in [('missing',missing), ('failed',failed), ('redirect',redirect), ('stream',stream)]:
        async def endpoint(request, fn=fn):
            return await fn()
        app.router.routes.insert(0, Route('/__header_test/' + path, endpoint))

    def checked(response, status):
        assert response.status_code == status, (response.status_code, response.text)
        for key, value in HEADERS.items():
            assert response.headers.get(key) == value, (response.url, key)
            assert len(response.headers.get_list(key)) == 1, key
        assert response.headers['strict-transport-security'] == 'max-age=31536000; includeSubDomains'
        return response

    with TestClient(app, base_url='https://testserver', raise_server_exceptions=False) as c:
        for path in ['/', '/index.html', '/admin', '/admin-static/admin.js', '/static/sw.js', '/api/health']:
            checked(c.get(path), 200)
        checked(c.head('/'), 200)
        assert not c.head('/').content
        for path in ['/static/app.js', '/static/styles.css']:
            gz = checked(c.get(path, headers={'Accept-Encoding':'gzip'}), 200)
            assert gz.headers['content-encoding'] == 'gzip'
            plain = checked(c.get(path, headers={'Accept-Encoding':'identity'}), 200)
            assert gz.content == plain.content
            assert 'immutable' in gz.headers['cache-control']
            assert 'Accept-Encoding' in gz.headers['vary']
            cached = checked(c.get(path, headers={'If-None-Match': gz.headers['etag']}), 304)
            assert not cached.content
            head = checked(c.head(path, headers={'Accept-Encoding':'identity'}), 200)
            assert not head.content
            assert int(head.headers['content-length']) == len(plain.content)
        checked(c.get('/__header_test/missing'), 404)
        checked(c.get('/__header_test/failed'), 500)
        checked(c.get('/__header_test/redirect', follow_redirects=False), 307)
        assert checked(c.get('/__header_test/stream'), 200).content == b'firstsecond'
        checked(c.post('/api/auth/pin', headers={'Sec-Fetch-Site':'cross-site'}, json={}), 403)
        checked(c.post('/api/auth/pin', headers={'Origin':'https://untrusted.invalid'}, json={}), 403)
        checked(c.post('/api/auth/pin', json={}), 422)
        checked(c.get('/api/me'), 401)
        assert checked(c.get('/api/health'), 200).headers['cache-control'] == 'no-store'
    print('JJ_RESPONSE_SECURITY_OK html/static/api/errors/head/304/gzip/stream')

if __name__ == '__main__':
    main()
