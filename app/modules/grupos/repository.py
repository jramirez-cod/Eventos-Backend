from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.empresas.models import Empresa
from app.modules.grupos.models import Grupo


class GrupoRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(
        self,
        id_grupo: int,
        *,
        for_update: bool = False,
    ) -> Grupo | None:
        stmt = select(Grupo).where(Grupo.id_grupo == id_grupo)
        if for_update:
            stmt = stmt.with_for_update()
        return await self.db.scalar(stmt)

    async def get_by_name(self, nombre_grupo: str) -> Grupo | None:
        stmt = select(Grupo).where(Grupo.nombre_grupo == nombre_grupo)
        return await self.db.scalar(stmt)

    async def create(
        self,
        *,
        nombre_grupo: str,
        descripcion: str | None,
        requiere_categoria: bool,
    ) -> Grupo:
        grupo = Grupo(
            nombre_grupo=nombre_grupo,
            descripcion=descripcion,
            requiere_categoria=requiere_categoria,
            estado=True,
        )
        self.db.add(grupo)
        await self.db.flush()
        return grupo

    async def update_estado(self, grupo: Grupo, estado: bool) -> Grupo:
        grupo.estado = estado
        await self.db.flush()
        return grupo

    async def update_requiere_categoria(
        self,
        grupo: Grupo,
        requiere_categoria: bool,
    ) -> Grupo:
        grupo.requiere_categoria = requiere_categoria
        await self.db.flush()
        return grupo

    async def get_active_companies_by_group(
        self,
        id_grupo: int,
    ) -> list[Empresa]:
        stmt = (
            select(Empresa)
            .where(
                Empresa.id_grupo == id_grupo,
                Empresa.estado.is_(True),
            )
            .order_by(Empresa.nombre_empresa, Empresa.id_empresa)
        )
        result = await self.db.scalars(stmt)
        return list(result.all())
