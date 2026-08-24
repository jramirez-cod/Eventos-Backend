from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.categorias.models import Categoria, DetalleCategoria
from app.modules.contactos.models import Contacto
from app.modules.empresas.models import Empresa
from app.modules.eventos.models import Evento
from app.modules.grupos.models import Grupo
from app.modules.participantes.models import (
    ConfirmacionParticipante,
    EventoEmpresa,
    Participante,
)


@dataclass(frozen=True, slots=True)
class EventoEmpresaDetalle:
    evento_empresa: EventoEmpresa
    evento: Evento
    empresa: Empresa
    grupo: Grupo
    categoria: Categoria


@dataclass(frozen=True, slots=True)
class ParticipanteDetalle:
    participante: Participante
    evento: Evento
    evento_empresa: EventoEmpresa
    empresa: Empresa
    contacto: Contacto


class ParticipanteRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_evento(self, id_evento: int) -> Evento | None:
        return await self.db.get(Evento, id_evento)

    async def get_evento_for_update(self, id_evento: int) -> Evento | None:
        stmt = (
            select(Evento)
            .where(Evento.id_evento == id_evento)
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
        self, *, id_evento: int, id_empresa: int
    ) -> EventoEmpresa | None:
        stmt = select(EventoEmpresa).where(
            EventoEmpresa.id_evento == id_evento,
            EventoEmpresa.id_empresa == id_empresa,
        )
        return await self.db.scalar(stmt)

    async def get_evento_empresa_by_id(
        self,
        id_evento_empresa: int,
        *,
        id_evento: int | None = None,
        for_update: bool = False,
    ) -> EventoEmpresa | None:
        stmt = select(EventoEmpresa).where(
            EventoEmpresa.id_evento_empresa == id_evento_empresa
        )
        if id_evento is not None:
            stmt = stmt.where(EventoEmpresa.id_evento == id_evento)
        if for_update:
            stmt = stmt.with_for_update()
        return await self.db.scalar(stmt)

    async def create_evento_empresa(
        self, *, id_evento: int, id_empresa: int, creado_por: int
    ) -> EventoEmpresa:
        evento_empresa = EventoEmpresa(
            id_evento=id_evento,
            id_empresa=id_empresa,
            estado=True,
            creado_por=creado_por,
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

    async def list_empresas_evento(
        self, id_evento: int
    ) -> list[EventoEmpresaDetalle]:
        stmt = (
            self._evento_empresa_select()
            .where(EventoEmpresa.id_evento == id_evento)
            .order_by(Empresa.nombre_empresa, EventoEmpresa.id_evento_empresa)
        )
        rows = (await self.db.execute(stmt)).all()
        return [self._to_evento_empresa_detalle(row) for row in rows]

    async def get_participante_by_evento_contacto(
        self, *, id_evento: int, id_contacto: int
    ) -> Participante | None:
        stmt = select(Participante).where(
            Participante.id_evento == id_evento,
            Participante.id_contacto == id_contacto,
        )
        return await self.db.scalar(stmt)

    async def get_existing_contact_ids(
        self, *, id_evento: int, ids_contacto: list[int]
    ) -> set[int]:
        stmt = select(Participante.id_contacto).where(
            Participante.id_evento == id_evento,
            Participante.id_contacto.in_(ids_contacto),
        )
        return set((await self.db.scalars(stmt)).all())

    async def create_participante(
        self,
        *,
        id_evento_empresa: int,
        id_evento: int,
        id_contacto: int,
        creado_por: int,
    ) -> Participante:
        participante = Participante(
            id_evento_empresa=id_evento_empresa,
            id_evento=id_evento,
            id_contacto=id_contacto,
            confirmacion=ConfirmacionParticipante.SIN_RESPUESTA,
            estado=True,
            creado_por=creado_por,
        )
        self.db.add(participante)
        await self.db.flush()
        return participante

    async def get_participante_detalle(
        self, id_participante: int
    ) -> ParticipanteDetalle | None:
        stmt = self._participante_select().where(
            Participante.id_participante == id_participante
        )
        row = (await self.db.execute(stmt)).first()
        return self._to_participante_detalle(row) if row else None

    async def list_participantes(
        self,
        *,
        id_evento: int | None,
        id_empresa: int | None,
        id_contacto: int | None,
        confirmacion: ConfirmacionParticipante | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[ParticipanteDetalle], int]:
        filters = self._participante_filters(
            id_evento=id_evento,
            id_empresa=id_empresa,
            id_contacto=id_contacto,
            confirmacion=confirmacion,
            search=search,
        )
        count_stmt = (
            select(func.count())
            .select_from(Participante)
            .join(
                EventoEmpresa,
                EventoEmpresa.id_evento_empresa
                == Participante.id_evento_empresa,
            )
            .join(Contacto, Contacto.id_contacto == Participante.id_contacto)
            .where(*filters)
        )
        total = int(await self.db.scalar(count_stmt) or 0)
        stmt = (
            self._participante_select()
            .where(*filters)
            .order_by(
                Contacto.apellidos,
                Contacto.nombres,
                Participante.id_participante,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).all()
        return [self._to_participante_detalle(row) for row in rows], total

    @staticmethod
    def _evento_empresa_select() -> Select[Any]:
        return (
            select(EventoEmpresa, Evento, Empresa, Grupo, Categoria)
            .join(Evento, Evento.id_evento == EventoEmpresa.id_evento)
            .join(Empresa, Empresa.id_empresa == EventoEmpresa.id_empresa)
            .join(
                DetalleCategoria,
                DetalleCategoria.id_detalle_categoria
                == Empresa.id_detalle_categoria,
            )
            .join(Grupo, Grupo.id_grupo == DetalleCategoria.id_grupo)
            .join(Categoria, Categoria.id_categoria == DetalleCategoria.id_categoria)
        )

    @staticmethod
    def _participante_select() -> Select[Any]:
        return (
            select(Participante, Evento, EventoEmpresa, Empresa, Contacto)
            .join(Evento, Evento.id_evento == Participante.id_evento)
            .join(
                EventoEmpresa,
                EventoEmpresa.id_evento_empresa
                == Participante.id_evento_empresa,
            )
            .join(Empresa, Empresa.id_empresa == EventoEmpresa.id_empresa)
            .join(Contacto, Contacto.id_contacto == Participante.id_contacto)
        )

    @staticmethod
    def _to_evento_empresa_detalle(row: Any) -> EventoEmpresaDetalle:
        return EventoEmpresaDetalle(
            evento_empresa=row[0],
            evento=row[1],
            empresa=row[2],
            grupo=row[3],
            categoria=row[4],
        )

    @staticmethod
    def _to_participante_detalle(row: Any) -> ParticipanteDetalle:
        return ParticipanteDetalle(
            participante=row[0],
            evento=row[1],
            evento_empresa=row[2],
            empresa=row[3],
            contacto=row[4],
        )

    @staticmethod
    def _participante_filters(
        *,
        id_evento: int | None,
        id_empresa: int | None,
        id_contacto: int | None,
        confirmacion: ConfirmacionParticipante | None,
        search: str | None,
    ) -> list[Any]:
        filters: list[Any] = []
        if id_evento is not None:
            filters.append(Participante.id_evento == id_evento)
        if id_empresa is not None:
            filters.append(EventoEmpresa.id_empresa == id_empresa)
        if id_contacto is not None:
            filters.append(Participante.id_contacto == id_contacto)
        if confirmacion is not None:
            filters.append(Participante.confirmacion == confirmacion)
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    Contacto.nombres.ilike(pattern),
                    Contacto.apellidos.ilike(pattern),
                    Contacto.numero_documento.ilike(pattern),
                )
            )
        return filters
