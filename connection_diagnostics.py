"""Payload-free ASGI diagnostics; no database reads or gameplay changes."""
import hashlib
import hmac
import json
import logging
import secrets
import time
from collections import OrderedDict

LOG = logging.getLogger('uvicorn.error')


class ConnectionDiagnostics:
    def __init__(self, app):
        self.app = app
        self.key = secrets.token_bytes(32)
        self.closed = OrderedDict()

    def emit(self, event, **fields):
        try:
            LOG.info('jj_connection %s', json.dumps(dict(event=event, **fields), separators=(',', ':')))
        except Exception:
            pass  # Diagnostics must never interrupt delivery or cleanup.

    def fingerprint(self, value):
        return hmac.new(self.key, value, hashlib.sha256).hexdigest()[:20]

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')
        kind = scope['type']
        headers = dict(scope.get('headers', []))
        if kind == 'http' and path == '/api/quiz/question':
            request_id = secrets.token_hex(8)
            source = headers.get(b'x-jj-quiz-source', b'').decode('ascii', 'ignore')
            if source not in {f'browser-call-{n}' for n in range(1, 20)}:
                source = 'unmarked'
            ua = headers.get(b'user-agent', b'').lower()
            agent = ('browser' if b'mozilla/' in ua else 'python' if b'python' in ua
                     else 'curl' if b'curl/' in ua else 'other')
            async def http_send(message):
                if message['type'] == 'http.response.start':
                    self.emit('quiz_response', request_id=request_id, status=message['status'],
                              source=source, agent=agent,
                              fetch_site=headers.get(b'sec-fetch-site', b'') in (b'same-origin', b'same-site'),
                              credentials_present=bool(headers.get(b'cookie') or headers.get(b'authorization')))
                await send(message)
            return await self.app(scope, receive, http_send)
        parts = path.strip('/').split('/')
        if kind == 'http' and len(parts) in (3, 4) and parts[:2] == ['api', 'tables']:
            operation = 'state_fetch' if len(parts) == 3 and scope.get('method') == 'GET' else (
                'action' if len(parts) == 4 and parts[3] == 'action' and scope.get('method') == 'POST' else None)
            if operation:
                credential = headers.get(b'cookie') or headers.get(b'authorization')
                async def table_send(message):
                    if message['type'] == 'http.response.start':
                        self.emit('table_http', operation=operation, status=message['status'],
                                  table_ref=self.fingerprint(('/ws/tables/' + parts[2]).encode()),
                                  session_ref=self.fingerprint(credential) if credential else None)
                    await send(message)
                return await self.app(scope, receive, table_send)
        if kind != 'websocket' or not path.startswith('/ws/tables/'):
            return await self.app(scope, receive, send)
        connection_id = secrets.token_hex(8)
        table = self.fingerprint(path.encode())
        credential = headers.get(b'cookie') or headers.get(b'authorization')
        peer = self.fingerprint(credential) if credential else None
        reconnect_key = (table, peer) if peer else None
        started = time.monotonic()
        previous = self.closed.get(reconnect_key) if reconnect_key else None
        previous = previous if previous and started - previous[1] <= 300 else None
        context = dict(connection_id=connection_id, table_ref=table, session_ref=peer,
                       previous_connection_id=previous[0] if previous else None)
        accepted = False
        code = None
        last_ping = None
        last_state_at = None
        snapshot = {}
        error = None
        self.emit('ws_start', **context)

        async def ws_receive():
            nonlocal code, last_ping
            message = await receive()
            if message['type'] == 'websocket.disconnect':
                code = message.get('code')
            elif message.get('text') == 'ping':
                last_ping = time.monotonic()
            return message

        async def ws_send(message):
            nonlocal accepted, code, snapshot, last_state_at
            await send(message)
            if message['type'] == 'websocket.accept':
                accepted = True
                self.emit('ws_accepted', **context)
            elif message['type'] == 'websocket.close':
                code = message.get('code')
            elif message['type'] == 'websocket.send' and message.get('text'):
                try:
                    frame = json.loads(message['text'])
                    if frame.get('type') == 'state' and isinstance(frame.get('state'), dict):
                        state = frame['state']
                        hand = state.get('hand') or {}
                        snapshot = {k: hand[k] for k in ('phase', 'action_seat', 'action_deadline')
                                    if k in hand and isinstance(hand[k], (str, int, float, type(None)))}
                        snapshot['hand_ref'] = self.fingerprint(str(hand['id']).encode()) if hand.get('id') else None
                        snapshot['can_act'] = bool((state.get('legal') or {}).get('can_act'))
                        first = last_state_at is None
                        last_state_at = time.monotonic()
                        if first:
                            self.emit('ws_first_state', **context, **snapshot)
                except (ValueError, TypeError, AttributeError):
                    pass
        try:
            return await self.app(scope, ws_receive, ws_send)
        except BaseException as exc:
            error = type(exc).__name__
            raise
        finally:
            now = time.monotonic()
            self.emit('ws_end', **context, accepted=accepted, code=code, error=error,
                      duration_ms=round((now-started)*1000),
                      last_ping_age_ms=round((now-last_ping)*1000) if last_ping else None,
                      last_state_age_ms=round((now-last_state_at)*1000) if last_state_at else None,
                      last_delivered_state=snapshot)
            if reconnect_key and last_state_at is not None:
                self.closed[reconnect_key] = (connection_id, now)
                self.closed.move_to_end(reconnect_key)
                while len(self.closed) > 2048:
                    self.closed.popitem(last=False)
