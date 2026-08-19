from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.categorias.models import Categoria, DetalleCategoria
from app.modules.empresas.models import Empresa
from app.modules.grupos.models import Grupo


CATEGORIA_SIN_CATEGORIA = "Sin categoría"


class CategoriaRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, id_categoria: int) -> Categoria | None:
        return await self.db.get(Categoria, id_categoria)

    async def get_by_nombre(self, nombre_categoria: str) -> Categoria | None:
        stmt = select(Categoria).where(Categoria.nombre_categoria == nombre_categoria)
        return await self.db.scalar(stmt)

    async def list_all(self) -> list[Categoria]:
        sin_categoria_primero = case(
            (Categoria.nombre_categoria == CATEGORIA_SIN_CATEGORIA, 0),
            else_=1,
        )
        stmt = select(Categoria).order_by(
            sin_categoria_primero, Categoria.id_categoria.desc()
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self, *, nombre_categoria: str, descripcion: str | None
    ) -> Categoria:
        categoria = Categoria(
            nombre_categoria=nombre_categoria,
            descripcion=descripcion,
            estado=True,
        )
        self.db.add(categoria)
        await self.db.flush()
        return categoria

    async def set_estado(self, categoria: Categoria, *, estado: bool) -> Categoria:
        categoria.estado = estado
        await self.db.flush()
        return categoria

    async def list_empresas_activas_usando(self, id_categoria: int) -> list[Empresa]:
        stmt = (
            select(Empresa)
            .join(
                DetalleCategoria,
                DetalleCategoria.id_detalle_categoria == Empresa.id_detalle_categoria,
            )
            .where(
                DetalleCategoria.id_categoria == id_categoria,
                Empresa.estado.is_(True),
            )
            .distinct()
            .order_by(Empresa.nombre_empresa)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_detalle(
        self, *, id_grupo: int, id_categoria: int
    ) -> DetalleCategoria | None:
        stmt = select(DetalleCategoria).where(
            DetalleCategoria.id_grupo == id_grupo,
            DetalleCategoria.id_categoria == id_categoria,
        )
        return await self.db.scalar(stmt)

    async def get_detalle_completo_by_id(
        self, id_detalle_categoria: int
    ) -> tuple[DetalleCategoria, Grupo, Categoria] | None:
        stmt = (
            select(DetalleCategoria, Grupo, Categoria)
            .join(Grupo, Grupo.id_grupo == DetalleCategoria.id_grupo)
            .join(Categoria, Categoria.id_categoria == DetalleCategoria.id_categoria)
            .where(DetalleCategoria.id_detalle_categoria == id_detalle_categoria)
        )
        result = await self.db.execute(stmt)
        row = result.first()
        return (row[0], row[1], row[2]) if row else None

    async def list_detalles_by_grupo(
        self, *, id_grupo: int, solo_activos: bool = True
    ) -> list[tuple[DetalleCategoria, Categoria]]:
        sin_categoria_primero = case(
            (Categoria.nombre_categoria == CATEGORIA_SIN_CATEGORIA, 0),
            else_=1,
        )
        stmt = (
            select(DetalleCategoria, Categoria)
            .join(Categoria, Categoria.id_categoria == DetalleCategoria.id_categoria)
            .where(DetalleCategoria.id_grupo == id_grupo)
            .order_by(sin_categoria_primero, Categoria.id_categoria.desc())
        )
        if solo_activos:
            stmt = stmt.where(DetalleCategoria.estado.is_(True))
        result = await self.db.execute(stmt)
        return [(detalle, categoria) for detalle, categoria in result.all()]

    async def create_detalle(
        self, *, id_grupo: int, id_categoria: int
    ) -> DetalleCategoria:
        detalle = DetalleCategoria(
            id_grupo=id_grupo,
            id_categoria=id_categoria,
            estado=True,
        )
        self.db.add(detalle)
        await self.db.flush()
        return detalle

    async def set_detalle_estado(
        self, detalle: DetalleCategoria, *, estado: bool
    ) -> DetalleCategoria:
        detalle.estado = estado
        await self.db.flush()
        return detalle
