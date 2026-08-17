from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.categorias.models import Categoria, DetalleCategoria
from app.modules.empresas.models import Empresa


class CategoriaRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(
        self,
        id_categoria: int,
        *,
        for_update: bool = False,
    ) -> Categoria | None:
        stmt = select(Categoria).where(Categoria.id_categoria == id_categoria)
        if for_update:
            stmt = stmt.with_for_update()
        return await self.db.scalar(stmt)

    async def get_by_name(self, nombre_categoria: str) -> Categoria | None:
        stmt = select(Categoria).where(
            Categoria.nombre_categoria == nombre_categoria
        )
        return await self.db.scalar(stmt)

    async def create_category(
        self,
        *,
        nombre_categoria: str,
        descripcion: str | None,
    ) -> Categoria:
        categoria = Categoria(
            nombre_categoria=nombre_categoria,
            descripcion=descripcion,
            estado=True,
        )
        self.db.add(categoria)
        await self.db.flush()
        return categoria

    async def get_detail_by_group_and_category(
        self,
        *,
        id_grupo: int,
        id_categoria: int,
    ) -> DetalleCategoria | None:
        stmt = select(DetalleCategoria).where(
            DetalleCategoria.id_grupo == id_grupo,
            DetalleCategoria.id_categoria == id_categoria,
        )
        return await self.db.scalar(stmt)

    async def create_detail(
        self,
        *,
        id_grupo: int,
        id_categoria: int,
    ) -> DetalleCategoria:
        detail = DetalleCategoria(
            id_grupo=id_grupo,
            id_categoria=id_categoria,
            estado=True,
        )
        self.db.add(detail)
        await self.db.flush()
        return detail

    async def get_details_by_category(
        self,
        id_categoria: int,
    ) -> list[DetalleCategoria]:
        stmt = select(DetalleCategoria).where(
            DetalleCategoria.id_categoria == id_categoria
        )
        result = await self.db.scalars(stmt)
        return list(result.all())

    async def get_active_companies_by_category(
        self,
        id_categoria: int,
    ) -> list[Empresa]:
        stmt = (
            select(Empresa)
            .join(
                DetalleCategoria,
                Empresa.id_detalle_categoria
                == DetalleCategoria.id_detalle_categoria,
            )
            .where(
                DetalleCategoria.id_categoria == id_categoria,
                Empresa.estado.is_(True),
            )
            .order_by(Empresa.nombre_empresa, Empresa.id_empresa)
        )
        result = await self.db.scalars(stmt)
        return list(result.all())

    async def update_estado(
        self,
        categoria: Categoria,
        estado: bool,
    ) -> Categoria:
        categoria.estado = estado
        await self.db.flush()
        return categoria
