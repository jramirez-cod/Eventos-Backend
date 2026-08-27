from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contactos.models import Contacto, ContactoHistorialEmpresa
from app.modules.empresas.models import Empresa
from app.modules.maestros.models import Cargo
from app.modules.usuarios.models import TipoDocumento


@dataclass(frozen=True, slots=True)
class ContactoDetalle:
    contacto: Contacto
    empresa: Empresa
    cargo: Cargo | None
    tipo_documento: TipoDocumento | None


class ContactoRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, id_contacto: int) -> Contacto | None:
        return await self.db.get(Contacto, id_contacto)

    async def get_by_id_for_update(self, id_contacto: int) -> Contacto | None:
        stmt = (
            select(Contacto)
            .where(Contacto.id_contacto == id_contacto)
            .with_for_update()
        )
        return await self.db.scalar(stmt)

    async def get_detallado(self, id_contacto: int) -> ContactoDetalle | None:
        stmt = self._detalle_select().where(Contacto.id_contacto == id_contacto)
        row = (await self.db.execute(stmt)).first()
        return self._to_detalle(row) if row else None

    async def get_by_documento(
        self, numero_documento: str, *, exclude_id: int | None = None
    ) -> Contacto | None:
        stmt = select(Contacto).where(
            Contacto.numero_documento == numero_documento
        )
        if exclude_id is not None:
            stmt = stmt.where(Contacto.id_contacto != exclude_id)
        return await self.db.scalar(stmt)

    async def get_empresa(self, id_empresa: int) -> Empresa | None:
        return await self.db.get(Empresa, id_empresa)

    async def get_cargo(self, id_cargo: int) -> Cargo | None:
        return await self.db.get(Cargo, id_cargo)

    async def get_tipo_documento(
        self, id_tipo_documento: int
    ) -> TipoDocumento | None:
        return await self.db.get(TipoDocumento, id_tipo_documento)

    async def create(
        self,
        *,
        id_empresa: int,
        id_cargo: int | None,
        id_tipo_documento: int | None,
        numero_documento: str | None,
        nombres: str,
        apellidos: str,
        genero: str,
        celular: str | None,
        correo: str | None,
        es_contacto_principal: bool,
    ) -> Contacto:
        contacto = Contacto(
            id_empresa=id_empresa,
            id_cargo=id_cargo,
            id_tipo_documento=id_tipo_documento,
            numero_documento=numero_documento,
            nombres=nombres,
            apellidos=apellidos,
            genero=genero,
            celular=celular,
            correo=correo,
            es_contacto_principal=es_contacto_principal,
            estado=True,
        )
        self.db.add(contacto)
        await self.db.flush()
        return contacto

    async def update(self, contacto: Contacto, values: dict[str, Any]) -> Contacto:
        for field, value in values.items():
            setattr(contacto, field, value)
        await self.db.flush()
        return contacto

    async def set_estado(self, contacto: Contacto, *, estado: bool) -> Contacto:
        contacto.estado = estado
        await self.db.flush()
        return contacto

    async def unset_contacto_principal(
        self, *, id_empresa: int, exclude_id: int | None = None
    ) -> None:
        stmt = select(Contacto).where(
            Contacto.id_empresa == id_empresa,
            Contacto.es_contacto_principal.is_(True),
        )
        if exclude_id is not None:
            stmt = stmt.where(Contacto.id_contacto != exclude_id)
        otros = list((await self.db.scalars(stmt)).all())
        for otro in otros:
            otro.es_contacto_principal = False
        if otros:
            await self.db.flush()

    async def get_contacto_principal(self, id_empresa: int) -> Contacto | None:
        stmt = select(Contacto).where(
            Contacto.id_empresa == id_empresa,
            Contacto.es_contacto_principal.is_(True),
            Contacto.estado.is_(True),
        )
        return await self.db.scalar(stmt)

    async def cambiar_empresa(
        self, contacto: Contacto, *, id_empresa: int
    ) -> Contacto:
        contacto.id_empresa = id_empresa
        await self.db.flush()
        return contacto

    async def create_historial_empresa(
        self,
        *,
        id_contacto: int,
        id_empresa: int,
        id_usuario_cambio: int | None,
        motivo: str | None,
        fecha_inicio: datetime | None = None,
        fecha_fin: datetime | None = None,
    ) -> ContactoHistorialEmpresa:
        historial = ContactoHistorialEmpresa(
            id_contacto=id_contacto,
            id_empresa=id_empresa,
            id_usuario_cambio=id_usuario_cambio,
            fecha_inicio=fecha_inicio or datetime.now(UTC),
            fecha_fin=fecha_fin,
            motivo=motivo,
        )
        self.db.add(historial)
        await self.db.flush()
        return historial

    async def cerrar_historial_vigente(
        self, id_contacto: int, *, fecha_fin: datetime | None = None
    ) -> int:
        stmt = (
            select(ContactoHistorialEmpresa)
            .where(
                ContactoHistorialEmpresa.id_contacto == id_contacto,
                ContactoHistorialEmpresa.fecha_fin.is_(None),
            )
            .with_for_update()
        )
        vigentes = list((await self.db.scalars(stmt)).all())
        cierre = fecha_fin or datetime.now(UTC)
        for historial in vigentes:
            historial.fecha_fin = cierre
        if vigentes:
            await self.db.flush()
        return len(vigentes)

    async def list_historial_empresa(
        self, id_contacto: int
    ) -> list[ContactoHistorialEmpresa]:
        stmt = (
            select(ContactoHistorialEmpresa)
            .where(ContactoHistorialEmpresa.id_contacto == id_contacto)
            .order_by(ContactoHistorialEmpresa.fecha_inicio)
        )
        return list((await self.db.scalars(stmt)).all())

    async def list_detallado(
        self,
        *,
        search: str | None = None,
        id_empresa: int | None = None,
        id_cargo: int | None = None,
        numero_documento: str | None = None,
        estado: bool | None = None,
        page: int = 1,
        page_size: int | None = 20,
    ) -> tuple[list[ContactoDetalle], int]:
        filters = self._list_filters(
            search=search,
            id_empresa=id_empresa,
            id_cargo=id_cargo,
            numero_documento=numero_documento,
            estado=estado,
        )
        count_stmt = select(func.count()).select_from(Contacto).where(*filters)
        total = int(await self.db.scalar(count_stmt) or 0)

        stmt = self._detalle_select().where(*filters).order_by(
            Contacto.apellidos, Contacto.nombres, Contacto.id_contacto
        )
        if page_size is not None:
            stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        rows = (await self.db.execute(stmt)).all()
        return [self._to_detalle(row) for row in rows], total

    @staticmethod
    def _detalle_select() -> Select[Any]:
        return (
            select(Contacto, Empresa, Cargo, TipoDocumento)
            .join(Empresa, Empresa.id_empresa == Contacto.id_empresa)
            .outerjoin(Cargo, Cargo.id_cargo == Contacto.id_cargo)
            .outerjoin(
                TipoDocumento,
                TipoDocumento.id_tipo_documento == Contacto.id_tipo_documento,
            )
        )

    @staticmethod
    def _to_detalle(row: Any) -> ContactoDetalle:
        return ContactoDetalle(
            contacto=row[0],
            empresa=row[1],
            cargo=row[2],
            tipo_documento=row[3],
        )

    @staticmethod
    def _list_filters(
        *,
        search: str | None,
        id_empresa: int | None,
        id_cargo: int | None,
        numero_documento: str | None,
        estado: bool | None,
    ) -> list[Any]:
        filters: list[Any] = []
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    Contacto.nombres.ilike(pattern),
                    Contacto.apellidos.ilike(pattern),
                    Contacto.numero_documento.ilike(pattern),
                    Contacto.correo.ilike(pattern),
                    Contacto.celular.ilike(pattern),
                )
            )
        if id_empresa is not None:
            filters.append(Contacto.id_empresa == id_empresa)
        if id_cargo is not None:
            filters.append(Contacto.id_cargo == id_cargo)
        if numero_documento:
            filters.append(Contacto.numero_documento == numero_documento.strip())
        if estado is not None:
            filters.append(Contacto.estado.is_(estado))
        return filters
