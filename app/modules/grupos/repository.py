from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.categorias.models import DetalleCategoria
from app.modules.empresas.models import Empresa
from app.modules.grupos.models import Grupo


class GrupoRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, id_grupo: int) -> Grupo | None:
        return await self.db.get(Grupo, id_grupo)

    async def get_by_nombre(
        self, nombre_grupo: str, *, exclude_id: int | None = None
    ) -> Grupo | None:
        stmt = select(Grupo).where(
            func.lower(Grupo.nombre_grupo) == nombre_grupo.lower()
        )
        if exclude_id is not None:
            stmt = stmt.where(Grupo.id_grupo != exclude_id)
        return await self.db.scalar(stmt)

    async def list_all(self) -> list[Grupo]:
        stmt = select(Grupo).order_by(Grupo.id_grupo.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self, *, id_grupo: int, nombre_grupo: str, descripcion: str | None
    ) -> Grupo:
        grupo = Grupo(
            id_grupo=id_grupo,
            nombre_grupo=nombre_grupo,
            descripcion=descripcion,
            estado=True,
        )
        self.db.add(grupo)
        await self.db.flush()
        return grupo

    async def set_estado(self, grupo: Grupo, *, estado: bool) -> Grupo:
        grupo.estado = estado
        await self.db.flush()
        return grupo

    async def update(
        self,
        grupo: Grupo,
        *,
        nombre_grupo: str,
        descripcion: str | None,
    ) -> Grupo:
        grupo.nombre_grupo = nombre_grupo
        grupo.descripcion = descripcion
        await self.db.flush()
        return grupo

    async def list_empresas_activas_usando(self, id_grupo: int) -> list[Empresa]:
        stmt = (
            select(Empresa)
            .join(
                DetalleCategoria,
                DetalleCategoria.id_detalle_categoria == Empresa.id_detalle_categoria,
            )
            .where(
                DetalleCategoria.id_grupo == id_grupo,
                Empresa.estado.is_(True),
            )
            .distinct()
            .order_by(Empresa.nombre_empresa)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
