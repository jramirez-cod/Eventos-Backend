from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.modules.categorias.models import Categoria, DetalleCategoria
from app.modules.contactos.models import Contacto
from app.modules.empresas.models import Empresa
from app.modules.eventos.models import (
    DetalleProgramacionEvento,
    Evento,
    ProgramacionEvento,
)
from app.modules.grupos.models import Grupo
from app.modules.maestros.models import Beneficio
from app.modules.participantes.beneficio_evaluador import AsignacionUso
from app.modules.participantes.models import (
    AsignacionBeneficio,
    CodigoAccesoPrincipal,
    EventoContacto,
    EventoEmpresa,
    ParticipanteQr,
)


@dataclass(frozen=True, slots=True)
class EventoEmpresaDetalle:
    evento_empresa: EventoEmpresa
    empresa: Empresa
    grupo: Grupo
    categoria: Categoria
    contacto_principal: Contacto | None
    codigo_fecha_envio: datetime | None


@dataclass(frozen=True, slots=True)
class EventoContactoDetalle:
    evento_contacto: EventoContacto
    contacto: Contacto | None
    empresa: Empresa
    categoria: Categoria
    id_beneficio_asignado: int | None
    nombre_beneficio_asignado: str | None
    qr_enviado: bool


class ParticipanteRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_programacion(
        self, id_programacion_evento: int, *, for_update: bool = False
    ) -> ProgramacionEvento | None:
        stmt = select(ProgramacionEvento).where(
            ProgramacionEvento.id_programacion_evento == id_programacion_evento
        )
        if for_update:
            stmt = stmt.with_for_update()
        return await self.db.scalar(stmt)

    async def get_evento_by_programacion_for_update(
        self, id_programacion_evento: int
    ) -> Evento | None:
        stmt = (
            select(Evento)
            .join(
                ProgramacionEvento,
                ProgramacionEvento.id_evento == Evento.id_evento,
            )
            .where(
                ProgramacionEvento.id_programacion_evento == id_programacion_evento
            )
            .with_for_update()
        )
        return await self.db.scalar(stmt)

    async def get_empresa(self, id_empresa: int) -> Empresa | None:
        return await self.db.get(Empresa, id_empresa)

    async def get_contacto(self, id_contacto: int) -> Contacto | None:
        return await self.db.get(Contacto, id_contacto)

    async def get_contactos(self, ids_contacto: list[int]) -> list[Contacto]:
        stmt = select(Contacto).where(Contacto.id_contacto.in_(ids_contacto))
        return list((await self.db.scalars(stmt)).all())

    async def get_evento_empresa(
        self, *, id_programacion_evento: int, id_empresa: int
    ) -> EventoEmpresa | None:
        stmt = select(EventoEmpresa).where(
            EventoEmpresa.id_programacion_evento == id_programacion_evento,
            EventoEmpresa.id_empresa == id_empresa,
        )
        return await self.db.scalar(stmt)

    async def get_evento_empresa_activa(
        self, *, id_programacion_evento: int, id_empresa: int
    ) -> EventoEmpresa | None:
        stmt = select(EventoEmpresa).where(
            EventoEmpresa.id_programacion_evento == id_programacion_evento,
            EventoEmpresa.id_empresa == id_empresa,
            EventoEmpresa.estado.is_(True),
        )
        return await self.db.scalar(stmt)

    async def get_evento_empresa_by_id(
        self,
        id_evento_empresa: int,
        *,
        id_programacion_evento: int | None = None,
        for_update: bool = False,
    ) -> EventoEmpresa | None:
        stmt = select(EventoEmpresa).where(
            EventoEmpresa.id_evento_empresa == id_evento_empresa
        )
        if id_programacion_evento is not None:
            stmt = stmt.where(
                EventoEmpresa.id_programacion_evento == id_programacion_evento
            )
        if for_update:
            stmt = stmt.with_for_update()
        return await self.db.scalar(stmt)

    async def create_evento_empresa(
        self, *, id_programacion_evento: int, id_empresa: int
    ) -> EventoEmpresa:
        evento_empresa = EventoEmpresa(
            id_programacion_evento=id_programacion_evento,
            id_empresa=id_empresa,
            estado=True,
        )
        self.db.add(evento_empresa)
        await self.db.flush()
        return evento_empresa

    async def get_evento_empresa_detalle(
        self, id_evento_empresa: int
    ) -> EventoEmpresaDetalle | None:
        stmt = self._evento_empresa_select().where(
            EventoEmpresa.id_evento_empresa == id_evento_empresa
        )
        row = (await self.db.execute(stmt)).first()
        return self._to_evento_empresa_detalle(row) if row else None

    async def list_ids_evento_empresa(self, id_programacion_evento: int) -> list[int]:
        stmt = select(EventoEmpresa.id_evento_empresa).where(
            EventoEmpresa.id_programacion_evento == id_programacion_evento
        )
        return list((await self.db.scalars(stmt)).all())

    async def list_empresas_programacion(
        self, id_programacion_evento: int
    ) -> list[EventoEmpresaDetalle]:
        stmt = (
            self._evento_empresa_select()
            .where(EventoEmpresa.id_programacion_evento == id_programacion_evento)
            .order_by(Empresa.nombre_empresa, EventoEmpresa.id_evento_empresa)
        )
        rows = (await self.db.execute(stmt)).all()
        return [self._to_evento_empresa_detalle(row) for row in rows]

    async def get_evento_contacto_by_programacion_contacto(
        self, *, id_programacion_evento: int, id_contacto: int
    ) -> EventoContacto | None:
        stmt = select(EventoContacto).where(
            EventoContacto.id_programacion_evento == id_programacion_evento,
            EventoContacto.id_contacto == id_contacto,
        )
        return await self.db.scalar(stmt)

    async def get_existing_contact_ids(
        self, *, id_programacion_evento: int, ids_contacto: list[int]
    ) -> set[int]:
        stmt = select(EventoContacto.id_contacto).where(
            EventoContacto.id_programacion_evento == id_programacion_evento,
            EventoContacto.id_contacto.in_(ids_contacto),
        )
        return set((await self.db.scalars(stmt)).all())

    async def create_evento_contacto(
        self, *, id_programacion_evento: int, id_contacto: int, id_empresa: int
    ) -> EventoContacto:
        evento_contacto = EventoContacto(
            id_programacion_evento=id_programacion_evento,
            id_contacto=id_contacto,
            id_empresa=id_empresa,
            estado=True,
            requiere_coordinacion=True,
        )
        self.db.add(evento_contacto)
        await self.db.flush()
        return evento_contacto

    async def create_evento_contacto_invitado(
        self,
        *,
        id_programacion_evento: int,
        id_empresa: int,
        nombres: str,
        apellidos: str,
        numero_documento: str | None,
        correo: str | None,
        celular: str | None,
    ) -> EventoContacto:
        evento_contacto = EventoContacto(
            id_programacion_evento=id_programacion_evento,
            id_contacto=None,
            id_empresa=id_empresa,
            invitado_nombres=nombres,
            invitado_apellidos=apellidos,
            invitado_numero_documento=numero_documento,
            invitado_correo=correo,
            invitado_celular=celular,
            estado=True,
            requiere_coordinacion=True,
        )
        self.db.add(evento_contacto)
        await self.db.flush()
        return evento_contacto

    async def count_invitados_sin_registrar(
        self, *, id_programacion_evento: int, id_empresa: int
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(EventoContacto)
            .where(
                EventoContacto.id_programacion_evento == id_programacion_evento,
                EventoContacto.id_empresa == id_empresa,
                EventoContacto.id_contacto.is_(None),
            )
        )
        return int(await self.db.scalar(stmt) or 0)

    async def get_evento_contacto_by_id(
        self, id_evento_contacto: int, *, for_update: bool = False
    ) -> EventoContacto | None:
        stmt = select(EventoContacto).where(
            EventoContacto.id_evento_contacto == id_evento_contacto
        )
        if for_update:
            stmt = stmt.with_for_update()
        return await self.db.scalar(stmt)

    async def update_evento_contacto(
        self, evento_contacto: EventoContacto, values: dict[str, Any]
    ) -> EventoContacto:
        for field, value in values.items():
            setattr(evento_contacto, field, value)
        await self.db.flush()
        return evento_contacto

    async def delete_evento_contacto(self, evento_contacto: EventoContacto) -> None:
        await self.db.delete(evento_contacto)
        await self.db.flush()

    async def get_evento_contacto_detalle(
        self, id_evento_contacto: int
    ) -> EventoContactoDetalle | None:
        stmt = self._evento_contacto_select().where(
            EventoContacto.id_evento_contacto == id_evento_contacto
        )
        row = (await self.db.execute(stmt)).first()
        return self._to_evento_contacto_detalle(row) if row else None

    async def list_evento_contactos(
        self,
        *,
        id_programacion_evento: int | None,
        id_empresa: int | None,
        id_contacto: int | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[EventoContactoDetalle], int]:
        filters = self._evento_contacto_filters(
            id_programacion_evento=id_programacion_evento,
            id_empresa=id_empresa,
            id_contacto=id_contacto,
            search=search,
        )
        count_stmt = (
            select(func.count())
            .select_from(EventoContacto)
            .outerjoin(Contacto, Contacto.id_contacto == EventoContacto.id_contacto)
            .where(*filters)
        )
        total = int(await self.db.scalar(count_stmt) or 0)
        stmt = (
            self._evento_contacto_select()
            .where(*filters)
            .order_by(EventoContacto.id_evento_contacto.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).all()
        return [self._to_evento_contacto_detalle(row) for row in rows], total

    @staticmethod
    def _evento_empresa_select() -> Select[Any]:
        principal = aliased(Contacto)
        return (
            select(
                EventoEmpresa,
                Empresa,
                Grupo,
                Categoria,
                principal,
                CodigoAccesoPrincipal.fecha_envio,
            )
            .join(Empresa, Empresa.id_empresa == EventoEmpresa.id_empresa)
            .join(
                DetalleCategoria,
                DetalleCategoria.id_detalle_categoria
                == Empresa.id_detalle_categoria,
            )
            .join(Grupo, Grupo.id_grupo == DetalleCategoria.id_grupo)
            .join(Categoria, Categoria.id_categoria == DetalleCategoria.id_categoria)
            .outerjoin(
                principal, principal.id_contacto == EventoEmpresa.id_contacto_principal
            )
            .outerjoin(
                CodigoAccesoPrincipal,
                (
                    CodigoAccesoPrincipal.id_evento_empresa
                    == EventoEmpresa.id_evento_empresa
                )
                & CodigoAccesoPrincipal.estado.is_(True),
            )
        )

    @staticmethod
    def _evento_contacto_select() -> Select[Any]:
        return (
            select(
                EventoContacto,
                Contacto,
                Empresa,
                Categoria,
                AsignacionBeneficio.id_beneficio,
                Beneficio.nombre,
                ParticipanteQr.fecha_envio,
            )
            .outerjoin(Contacto, Contacto.id_contacto == EventoContacto.id_contacto)
            .join(Empresa, Empresa.id_empresa == EventoContacto.id_empresa)
            .join(
                DetalleCategoria,
                DetalleCategoria.id_detalle_categoria
                == Empresa.id_detalle_categoria,
            )
            .join(Categoria, Categoria.id_categoria == DetalleCategoria.id_categoria)
            .outerjoin(
                AsignacionBeneficio,
                AsignacionBeneficio.id_evento_contacto
                == EventoContacto.id_evento_contacto,
            )
            .outerjoin(
                Beneficio, Beneficio.id_beneficio == AsignacionBeneficio.id_beneficio
            )
            .outerjoin(
                ParticipanteQr,
                ParticipanteQr.id_evento_contacto
                == EventoContacto.id_evento_contacto,
            )
        )

    @staticmethod
    def _to_evento_empresa_detalle(row: Any) -> EventoEmpresaDetalle:
        return EventoEmpresaDetalle(
            evento_empresa=row[0],
            empresa=row[1],
            grupo=row[2],
            categoria=row[3],
            contacto_principal=row[4],
            codigo_fecha_envio=row[5],
        )

    @staticmethod
    def _to_evento_contacto_detalle(row: Any) -> EventoContactoDetalle:
        return EventoContactoDetalle(
            evento_contacto=row[0],
            contacto=row[1],
            empresa=row[2],
            categoria=row[3],
            id_beneficio_asignado=row[4],
            nombre_beneficio_asignado=row[5],
            qr_enviado=row[6] is not None,
        )

    # -- AsignacionBeneficio --------------------------------------------

    async def get_asignacion_beneficio(
        self, id_evento_contacto: int
    ) -> AsignacionBeneficio | None:
        stmt = select(AsignacionBeneficio).where(
            AsignacionBeneficio.id_evento_contacto == id_evento_contacto
        )
        return await self.db.scalar(stmt)

    async def create_asignacion_beneficio(
        self,
        *,
        id_evento_contacto: int,
        id_beneficio: int,
        codigo_grupo: str | None,
    ) -> AsignacionBeneficio:
        asignacion = AsignacionBeneficio(
            id_evento_contacto=id_evento_contacto,
            id_beneficio=id_beneficio,
            codigo_grupo=codigo_grupo,
        )
        self.db.add(asignacion)
        await self.db.flush()
        return asignacion

    async def delete_asignacion_beneficio(
        self, asignacion: AsignacionBeneficio
    ) -> None:
        await self.db.delete(asignacion)
        await self.db.flush()

    async def list_asignaciones_por_evento(
        self, *, id_programacion_evento: int, id_empresa: int, id_beneficio: int
    ) -> list[AsignacionUso]:
        stmt = (
            select(
                AsignacionBeneficio.id_asignacion_beneficio,
                AsignacionBeneficio.codigo_grupo,
                EventoContacto.asistencia_evento,
            )
            .join(
                EventoContacto,
                EventoContacto.id_evento_contacto
                == AsignacionBeneficio.id_evento_contacto,
            )
            .where(
                EventoContacto.id_programacion_evento == id_programacion_evento,
                EventoContacto.id_empresa == id_empresa,
                AsignacionBeneficio.id_beneficio == id_beneficio,
            )
        )
        rows = (await self.db.execute(stmt)).all()
        return [AsignacionUso(*row) for row in rows]

    async def list_asignaciones_por_anio(
        self,
        *,
        id_evento: int,
        id_empresa: int,
        id_beneficio: int,
        fecha_inicio: date,
        fecha_fin: date,
    ) -> list[AsignacionUso]:
        dentro_de_rango = (
            select(DetalleProgramacionEvento.id_detalle_programacion)
            .where(
                DetalleProgramacionEvento.id_programacion_evento
                == EventoContacto.id_programacion_evento,
                DetalleProgramacionEvento.fecha >= fecha_inicio,
                DetalleProgramacionEvento.fecha <= fecha_fin,
            )
            .exists()
        )
        stmt = (
            select(
                AsignacionBeneficio.id_asignacion_beneficio,
                AsignacionBeneficio.codigo_grupo,
                EventoContacto.asistencia_evento,
            )
            .join(
                EventoContacto,
                EventoContacto.id_evento_contacto
                == AsignacionBeneficio.id_evento_contacto,
            )
            .join(
                ProgramacionEvento,
                ProgramacionEvento.id_programacion_evento
                == EventoContacto.id_programacion_evento,
            )
            .where(
                ProgramacionEvento.id_evento == id_evento,
                EventoContacto.id_empresa == id_empresa,
                AsignacionBeneficio.id_beneficio == id_beneficio,
                dentro_de_rango,
            )
        )
        rows = (await self.db.execute(stmt)).all()
        return [AsignacionUso(*row) for row in rows]

    # -- ParticipanteQr ---------------------------------------------------

    async def create_participante_qr(
        self, *, id_evento_contacto: int, codigo_seguro: str
    ) -> ParticipanteQr:
        qr = ParticipanteQr(
            id_evento_contacto=id_evento_contacto,
            codigo_seguro=codigo_seguro,
            estado=True,
        )
        self.db.add(qr)
        await self.db.flush()
        return qr

    async def get_participante_qr_by_evento_contacto(
        self, id_evento_contacto: int
    ) -> ParticipanteQr | None:
        stmt = select(ParticipanteQr).where(
            ParticipanteQr.id_evento_contacto == id_evento_contacto,
            ParticipanteQr.estado.is_(True),
        )
        return await self.db.scalar(stmt)

    async def get_participante_qr_by_codigo(
        self, codigo_seguro: str
    ) -> ParticipanteQr | None:
        stmt = select(ParticipanteQr).where(
            ParticipanteQr.codigo_seguro == codigo_seguro,
            ParticipanteQr.estado.is_(True),
        )
        return await self.db.scalar(stmt)

    async def mark_qr_enviado(self, qr: ParticipanteQr) -> ParticipanteQr:
        qr.fecha_envio = datetime.now(timezone.utc)
        await self.db.flush()
        return qr

    async def list_ids_evento_contacto(
        self, id_programacion_evento: int
    ) -> list[int]:
        stmt = select(EventoContacto.id_evento_contacto).where(
            EventoContacto.id_programacion_evento == id_programacion_evento
        )
        return list((await self.db.scalars(stmt)).all())

    # -- Contacto principal -----------------------------------------------

    async def set_contacto_principal(
        self, evento_empresa: EventoEmpresa, *, id_contacto: int
    ) -> EventoEmpresa:
        evento_empresa.id_contacto_principal = id_contacto
        await self.db.flush()
        return evento_empresa

    # -- CodigoAccesoPrincipal ---------------------------------------------

    async def get_codigo_vigente(
        self, id_evento_empresa: int
    ) -> CodigoAccesoPrincipal | None:
        stmt = select(CodigoAccesoPrincipal).where(
            CodigoAccesoPrincipal.id_evento_empresa == id_evento_empresa,
            CodigoAccesoPrincipal.estado.is_(True),
        )
        return await self.db.scalar(stmt)

    async def get_codigo_by_hash(
        self, codigo_hash: str
    ) -> CodigoAccesoPrincipal | None:
        stmt = select(CodigoAccesoPrincipal).where(
            CodigoAccesoPrincipal.codigo_hash == codigo_hash,
            CodigoAccesoPrincipal.estado.is_(True),
        )
        return await self.db.scalar(stmt)

    async def invalidar_codigos(self, id_evento_empresa: int) -> None:
        stmt = select(CodigoAccesoPrincipal).where(
            CodigoAccesoPrincipal.id_evento_empresa == id_evento_empresa,
            CodigoAccesoPrincipal.estado.is_(True),
        )
        vigentes = list((await self.db.scalars(stmt)).all())
        for codigo in vigentes:
            codigo.estado = False
        await self.db.flush()

    async def create_codigo(
        self,
        *,
        id_evento_empresa: int,
        codigo_hash: str,
        expira_en: datetime,
    ) -> CodigoAccesoPrincipal:
        codigo = CodigoAccesoPrincipal(
            id_evento_empresa=id_evento_empresa,
            codigo_hash=codigo_hash,
            expira_en=expira_en,
            estado=True,
        )
        self.db.add(codigo)
        await self.db.flush()
        return codigo

    async def mark_codigo_enviado(
        self, codigo: CodigoAccesoPrincipal
    ) -> CodigoAccesoPrincipal:
        codigo.fecha_envio = datetime.now(timezone.utc)
        await self.db.flush()
        return codigo

    @staticmethod
    def _evento_contacto_filters(
        *,
        id_programacion_evento: int | None,
        id_empresa: int | None,
        id_contacto: int | None,
        search: str | None,
    ) -> list[Any]:
        filters: list[Any] = []
        if id_programacion_evento is not None:
            filters.append(
                EventoContacto.id_programacion_evento == id_programacion_evento
            )
        if id_empresa is not None:
            filters.append(EventoContacto.id_empresa == id_empresa)
        if id_contacto is not None:
            filters.append(EventoContacto.id_contacto == id_contacto)
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    Contacto.nombres.ilike(pattern),
                    Contacto.apellidos.ilike(pattern),
                    Contacto.numero_documento.ilike(pattern),
                    EventoContacto.invitado_nombres.ilike(pattern),
                    EventoContacto.invitado_apellidos.ilike(pattern),
                    EventoContacto.invitado_numero_documento.ilike(pattern),
                )
            )
        return filters
