import json
import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response

from . import models  # noqa: F401
from .api import router
from .config import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.3.0")
logger = logging.getLogger("jobflow.request")
REQUEST_COUNT = Counter(
    "jobflow_http_requests_total", "HTTP requests", ["method", "route", "status"]
)
REQUEST_LATENCY = Histogram(
    "jobflow_http_request_duration_seconds", "HTTP request latency", ["method", "route"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix=settings.api_prefix)


@app.middleware("http")
async def request_observability(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid4().hex
    started = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - started
    route = getattr(request.scope.get("route"), "path", request.url.path)
    REQUEST_COUNT.labels(request.method, route, response.status_code).inc()
    REQUEST_LATENCY.labels(request.method, route).observe(elapsed)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        json.dumps(
            {
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "route": route,
                "status": response.status_code,
                "duration_ms": round(elapsed * 1000, 2),
            },
            ensure_ascii=False,
        )
    )
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
