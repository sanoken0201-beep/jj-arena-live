# v1.18.1 admin route fix

The v1.18 admin console was installed after the legacy SPA catch-all route. Because Starlette resolves routes in declaration order, browser requests to `/admin` were served the normal JJ Arena SPA before the admin route could match.

v1.18.1 promotes only these isolated routes ahead of the catch-all:

- `/admin`
- `/admin/`
- `/admin-static/*`
- `/api/admin/console/*`

All other application route ordering is preserved.

Validation: `smoke_test_admin_route.py` directly exercises the ASGI application without external HTTP test dependencies and verifies the admin page, CSS, JavaScript, and unauthenticated admin API response. A Render smoke build completed with `ADMIN_ROUTE_SMOKE_OK`.
