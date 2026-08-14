from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
import sys
import asyncio

# On Windows, use the selector event loop for compatibility with psycopg async
if sys.platform == "win32":
    try:
        from asyncio import WindowsSelectorEventLoopPolicy

        asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.db.session import engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """
    Gestiona recursos globales de la aplicación.
    """
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.app_debug,
    lifespan=lifespan,
)

# Configuración de CORS para permitir peticiones desde el frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    api_router,
    prefix="/api/v1",
)


@app.get("/", tags=["Root"])
async def root() -> dict[str, str]:
    return {
        "application": settings.app_name,
        "version": settings.app_version,
        "documentation": "/docs",
    }
