"""
Request correlation IDs + request timing, as Flask before/after hooks.

Usage in app.py:
    from middleware import register_middleware
    register_middleware(app)

Then, inside any route, get the current request's ID with:
    from flask import g
    g.request_id
"""
import time
import uuid
from flask import request, g

from logger import get_logger

log = get_logger("gyaan_bhandar.http")


def register_middleware(app):

    @app.before_request
    def _start_timer_and_request_id():
        # Respect an inbound X-Request-ID (e.g. from a gateway/load balancer),
        # otherwise mint a new one.
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        g.start_time = time.perf_counter()

        log.info(
            "request_started",
            extra={
                "request_id": g.request_id,
                "method": request.method,
                "path": request.path,
            },
        )

    @app.after_request
    def _log_response_and_attach_header(response):
        duration_ms = round((time.perf_counter() - g.start_time) * 1000, 2)
        response.headers["X-Request-ID"] = g.request_id

        log.info(
            "request_finished",
            extra={
                "request_id": g.request_id,
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    @app.errorhandler(Exception)
    def _handle_uncaught_exception(err):
        request_id = getattr(g, "request_id", "unknown")
        log.error(
            "unhandled_exception",
            extra={"request_id": request_id, "error": str(err)},
            exc_info=err,
        )
        from flask import jsonify
        return jsonify({
            "error": "Internal server error",
            "request_id": request_id,
        }), 500