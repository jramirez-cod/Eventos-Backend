from datetime import UTC, datetime

from sqlalchemy import func, select
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
        page: int = 1,
        page_size: int | None = None,
    ) -> tuple[list[tuple[Empresa, Grupo, Categoria]], int]:
        base = (
            select(Empresa, Grupo, Categoria)
            .join(
                DetalleCategoria,
                DetalleCategoria.id_detalle_categoria == Empresa.id_detalle_categoria,
            )
            .join(Grupo, Grupo.id_grupo == DetalleCategoria.id_grupo)
            .join(Categoria, Categoria.id_categoria == DetalleCategoria.id_categoria)
        )
        if nombre:
            base = base.where(Empresa.nombre_empresa.ilike(f"%{nombre}%"))
        if ruc:
            base = base.where(Empresa.ruc == ruc)
        if id_grupo is not None:
            base = base.where(DetalleCategoria.id_grupo == id_grupo)
        if id_categoria is not None:
            base = base.where(DetalleCategoria.id_categoria == id_categoria)
        if estado is not None:
            base = base.where(Empresa.estado.is_(estado))

        total = int(
            await self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        )

        stmt = base.order_by(Empresa.id_empresa.desc())
        if page_size is not None:
            stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(stmt)
        rows = [(empresa, grupo, categoria) for empresa, grupo, categoria in result.all()]
        return rows, total

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

    async def update_general(
        self,
        empresa: Empresa,
        *,
        nombre_empresa: str,
        razon_social: str | None,
        nombre_comercial: str | None,
    ) -> Empresa:
        empresa.nombre_empresa = nombre_empresa
        empresa.razon_social = razon_social
        empresa.nombre_comercial = nombre_comercial
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
