from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db


router = APIRouter(
    prefix="/health",
    tags=["Health"],
)


@router.get("")
async def api_health() -> dict[str, str]:
    """
    Comprueba únicamente que la API esté respondiendo.
    """
    return {
        "status": "ok",
        "api": "available",
    }


@router.get("/database")
async def database_health(
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Ejecuta una consulta mínima para comprobar PostgreSQL.
    """
    try:
        result = await db.execute(text("SELECT 1"))
        value = result.scalar_one()

        if value != 1:
            raise RuntimeError("PostgreSQL devolvió un resultado inesperado.")

        return {
            "status": "ok",
            "database": "connected",
        }

    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo establecer conexión con PostgreSQL.",
        ) from exc
