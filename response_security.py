"""Apply the existing browser policy outside all responses, including HTTP 500."""
import os

from starlette.datastructures import MutableHeaders


HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws: wss:; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
}


class SecurityHeaders:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def secured_send(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in HEADERS.items():
                    headers[name] = value
                if os.getenv("RENDER"):
                    headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            await send(message)

        await self.app(scope, receive, secured_send)


def install(app):
    if getattr(app.state, "jj_response_security_installed", False):
        return
    if app.middleware_stack is not None:
        raise RuntimeError("response security must be installed before serving requests")
    build_stack = app.build_middleware_stack

    # add_middleware would sit INSIDE Starlette's ServerErrorMiddleware, missing
    # unhandled 500s. Wrap the lazily built complete stack instead, preserving
    # FastAPI's object identity, route registration and lifecycle handling.
    def build_secured_stack():
        return SecurityHeaders(build_stack())

    app.build_middleware_stack = build_secured_stack
    app.state.jj_response_security_installed = True
