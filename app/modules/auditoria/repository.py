from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auditoria.models import Auditoria


class AuditoriaRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        id_usuario: int | None,
        entidad: str,
        accion: str,
        id_modulo: int | None = None,
        id_entidad: int | str | None = None,
        valor_anterior: dict[str, Any] | None = None,
        valor_nuevo: dict[str, Any] | None = None,
        motivo: str | None = None,
    ) -> Auditoria | None:
        if not await self._table_exists():
            return None

        auditoria = Auditoria(
            id_usuario=id_usuario,
            id_modulo=id_modulo,
            entidad=entidad,
            id_entidad=str(id_entidad) if id_entidad is not None else None,
            accion=accion,
            valor_anterior=valor_anterior,
            valor_nuevo=valor_nuevo,
            motivo=motivo,
        )
        self.db.add(auditoria)
        await self.db.flush()
        return auditoria

    async def _table_exists(self) -> bool:
        result = await self.db.scalar(text("SELECT to_regclass('auditoria')"))
        return result is not None
