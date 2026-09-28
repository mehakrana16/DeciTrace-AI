"""DeciTrace AI — FastAPI application entry point.

Run locally:
    cd backend
    uvicorn app.main:app --reload --port 8000

OpenAPI docs: http://localhost:8000/docs
"""
from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routes import router
from .config import settings
from .data.db import init_db

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger("decitrace")

app = FastAPI(
    title=settings.APP_NAME,
    description=(
        f"{settings.TAGLINE}. {settings.PROBLEM_STATEMENT}.\n\n"
        "Deterministic business signals fused with retrieval-augmented evidence, "
        "producing prioritised, explainable, evidence-backed decisions that require "
        "human approval."
    ),
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time-Ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
    response.headers["X-Engine-Mode"] = "llm-assisted" if settings.llm_enabled else "deterministic"
    return response


@app.exception_handler(ValueError)
async def value_error_handler(_request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc), "error": "invalid_request"})


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    logger.info("%s v%s starting", settings.APP_NAME, settings.VERSION)
    logger.info("database       : %s", settings.DATABASE_URL)
    logger.info("embedding mode : %s", settings.EMBEDDING_BACKEND)
    logger.info("llm enabled    : %s", settings.llm_enabled)
    if not settings.llm_enabled:
        logger.info("LLM key absent — running in deterministic template mode (fully functional)")


app.include_router(router)


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {
        "app": settings.APP_NAME,
        "tagline": settings.TAGLINE,
        "problem_statement": settings.PROBLEM_STATEMENT,
        "version": settings.VERSION,
        "docs": "/docs",
        "health": "/api/health",
        "engine_mode": "llm-assisted" if settings.llm_enabled else "deterministic",
    }
