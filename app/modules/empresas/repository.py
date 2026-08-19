from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.categorias.models import Categoria, DetalleCategoria
from app.modules.empresas.models import Empresa, EmpresaHistorialClasificacion
from app.modules.grupos.models import Grupo


class EmpresaRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, id_empresa: int) -> Empresa | None:
        return await self.db.get(Empresa, id_empresa)

    async def get_by_ruc(self, ruc: str) -> Empresa | None:
        stmt = select(Empresa).where(Empresa.ruc == ruc)
        return await self.db.scalar(stmt)

    async def get_detallado(
        self, id_empresa: int
    ) -> tuple[Empresa, Grupo, Categoria] | None:
        stmt = (
            select(Empresa, Grupo, Categoria)
            .join(
                DetalleCategoria,
                DetalleCategoria.id_detalle_categoria == Empresa.id_detalle_categoria,
            )
            .join(Grupo, Grupo.id_grupo == DetalleCategoria.id_grupo)
            .join(Categoria, Categoria.id_categoria == DetalleCategoria.id_categoria)
            .where(Empresa.id_empresa == id_empresa)
        )
        result = await self.db.execute(stmt)
        row = result.first()
        return (row[0], row[1], row[2]) if row else None

    async def list_all_detallado(
        self,
        *,
        nombre: str | None = None,
        ruc: str | None = None,
        id_grupo: int | None = None,
        id_categoria: int | None = None,
        estado: bool | None = None,
    ) -> list[tuple[Empresa, Grupo, Categoria]]:
        stmt = (
            select(Empresa, Grupo, Categoria)
            .join(
                DetalleCategoria,
                DetalleCategoria.id_detalle_categoria == Empresa.id_detalle_categoria,
            )
            .join(Grupo, Grupo.id_grupo == DetalleCategoria.id_grupo)
            .join(Categoria, Categoria.id_categoria == DetalleCategoria.id_categoria)
            .order_by(Empresa.id_empresa.desc())
        )
        if nombre:
            stmt = stmt.where(Empresa.nombre_empresa.ilike(f"%{nombre}%"))
        if ruc:
            stmt = stmt.where(Empresa.ruc == ruc)
        if id_grupo is not None:
            stmt = stmt.where(DetalleCategoria.id_grupo == id_grupo)
        if id_categoria is not None:
            stmt = stmt.where(DetalleCategoria.id_categoria == id_categoria)
        if estado is not None:
            stmt = stmt.where(Empresa.estado.is_(estado))

        result = await self.db.execute(stmt)
        return [(empresa, grupo, categoria) for empresa, grupo, categoria in result.all()]

    async def create(
        self,
        *,
        nombre_empresa: str,
        ruc: str,
        id_detalle_categoria: int,
        razon_social: str | None,
        nombre_comercial: str | None,
    ) -> Empresa:
        empresa = Empresa(
            nombre_empresa=nombre_empresa,
            ruc=ruc,
            id_detalle_categoria=id_detalle_categoria,
            razon_social=razon_social,
            nombre_comercial=nombre_comercial,
            estado=True,
        )
        self.db.add(empresa)
        await self.db.flush()
        return empresa

    async def set_estado(self, empresa: Empresa, *, estado: bool) -> Empresa:
        empresa.estado = estado
        await self.db.flush()
        return empresa

    async def update_clasificacion(
        self, empresa: Empresa, *, id_detalle_categoria: int
    ) -> Empresa:
        empresa.id_detalle_categoria = id_detalle_categoria
        await self.db.flush()
        return empresa

    async def create_historial(
        self, *, id_empresa: int, id_detalle_categoria: int
    ) -> EmpresaHistorialClasificacion:
        historial = EmpresaHistorialClasificacion(
            id_empresa=id_empresa,
            id_detalle_categoria=id_detalle_categoria,
        )
        self.db.add(historial)
        await self.db.flush()
        return historial

    async def cerrar_historial_vigente(self, id_empresa: int) -> None:
        stmt = select(EmpresaHistorialClasificacion).where(
            EmpresaHistorialClasificacion.id_empresa == id_empresa,
            EmpresaHistorialClasificacion.fecha_fin.is_(None),
        )
        vigente = await self.db.scalar(stmt)
        if vigente is not None:
            vigente.fecha_fin = datetime.now(UTC)
            await self.db.flush()

    async def list_historial(
        self, id_empresa: int
    ) -> list[tuple[EmpresaHistorialClasificacion, Grupo, Categoria]]:
        stmt = (
            select(EmpresaHistorialClasificacion, Grupo, Categoria)
            .join(
                DetalleCategoria,
                DetalleCategoria.id_detalle_categoria
                == EmpresaHistorialClasificacion.id_detalle_categoria,
            )
            .join(Grupo, Grupo.id_grupo == DetalleCategoria.id_grupo)
            .join(Categoria, Categoria.id_categoria == DetalleCategoria.id_categoria)
            .where(EmpresaHistorialClasificacion.id_empresa == id_empresa)
            .order_by(EmpresaHistorialClasificacion.fecha_inicio.desc())
        )
        result = await self.db.execute(stmt)
        return [(h, g, c) for h, g, c in result.all()]
