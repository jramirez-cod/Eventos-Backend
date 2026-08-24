from dataclasses import dataclass
from datetime import date, time
from typing import Any

from sqlalchemy import Select, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.eventos.models import (
    DetalleProgramacionEvento,
    Evento,
    EventoEstado,
    EventoModalidad,
    Lugar,
    ProgramacionEvento,
)


@dataclass(frozen=True, slots=True)
class EventoDetalle:
    evento: Evento
    programacion: ProgramacionEvento
    lugar: Lugar | None


class EventoRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, id_evento: int) -> Evento | None:
        return await self.db.get(Evento, id_evento)

    async def get_by_id_for_update(self, id_evento: int) -> Evento | None:
        stmt = (
            select(Evento)
            .where(Evento.id_evento == id_evento)
            .with_for_update()
        )
        return await self.db.scalar(stmt)

    async def get_detallado(self, id_evento: int) -> EventoDetalle | None:
        stmt = self._detalle_select().where(Evento.id_evento == id_evento)
        row = (await self.db.execute(stmt)).first()
        return self._to_detalle(row) if row else None

    async def count_by_name(self, nombre_evento: str) -> int:
        stmt = select(func.count()).select_from(Evento).where(
            func.lower(Evento.nombre_evento) == nombre_evento.lower()
        )
        return int(await self.db.scalar(stmt) or 0)

    async def list_detallado(
        self,
        *,
        search: str | None,
        fecha_desde: date | None,
        fecha_hasta: date | None,
        estado: EventoEstado | None,
        modalidad: EventoModalidad | None,
        page: int,
        page_size: int | None,
    ) -> tuple[list[EventoDetalle], int]:
        filters = self._list_filters(
            search=search,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            estado=estado,
            modalidad=modalidad,
        )
        count_stmt = (
            select(func.count())
            .select_from(Evento)
            .join(
                ProgramacionEvento,
                ProgramacionEvento.id_evento == Evento.id_evento,
            )
            .where(*filters)
        )
        total = int(await self.db.scalar(count_stmt) or 0)

        stmt = (
            self._detalle_select()
            .where(*filters)
            .order_by(Evento.fecha_inicio.desc(), Evento.id_evento.desc())
        )
        if page_size is not None:
            stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        rows = (await self.db.execute(stmt)).all()
        return [self._to_detalle(row) for row in rows], total

    async def create_evento(
        self,
        *,
        nombre_evento: str,
        descripcion: str | None,
        fecha_inicio: date,
        fecha_fin: date,
        aforo: int | None,
        creado_por: int,
    ) -> Evento:
        evento = Evento(
            nombre_evento=nombre_evento,
            descripcion=descripcion,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            aforo=aforo,
            estado=EventoEstado.ABIERTO,
            creado_por=creado_por,
        )
        self.db.add(evento)
        await self.db.flush()
        return evento

    async def update_evento(
        self, evento: Evento, values: dict[str, Any]
    ) -> Evento:
        for field, value in values.items():
            setattr(evento, field, value)
        await self.db.flush()
        return evento

    async def create_lugar(
        self,
        *,
        pais: str | None,
        provincia: str | None,
        distrito: str | None,
        direccion: str | None,
    ) -> Lugar:
        lugar = Lugar(
            pais=pais,
            provincia=provincia,
            distrito=distrito,
            direccion=direccion,
            estado=True,
        )
        self.db.add(lugar)
        await self.db.flush()
        return lugar

    async def update_lugar(self, lugar: Lugar, values: dict[str, Any]) -> Lugar:
        for field, value in values.items():
            setattr(lugar, field, value)
        await self.db.flush()
        return lugar

    async def create_programacion(
        self,
        *,
        id_evento: int,
        id_lugar: int | None,
        modalidad: EventoModalidad,
        enlace_general: str | None,
    ) -> ProgramacionEvento:
        programacion = ProgramacionEvento(
            id_evento=id_evento,
            id_lugar=id_lugar,
            modalidad=modalidad,
            enlace_general=enlace_general,
            estado=True,
        )
        self.db.add(programacion)
        await self.db.flush()
        return programacion

    async def get_programacion(
        self, id_evento: int, *, for_update: bool = False
    ) -> ProgramacionEvento | None:
        stmt = select(ProgramacionEvento).where(
            ProgramacionEvento.id_evento == id_evento
        )
        if for_update:
            stmt = stmt.with_for_update()
        return await self.db.scalar(stmt)

    async def update_programacion(
        self, programacion: ProgramacionEvento, values: dict[str, Any]
    ) -> ProgramacionEvento:
        for field, value in values.items():
            setattr(programacion, field, value)
        await self.db.flush()
        return programacion

    async def create_dia(
        self,
        *,
        id_programacion_evento: int,
        fecha: date,
        hora_inicio: time,
        hora_fin: time | None,
        enlace: str | None,
    ) -> DetalleProgramacionEvento:
        dia = DetalleProgramacionEvento(
            id_programacion_evento=id_programacion_evento,
            fecha=fecha,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            enlace=enlace,
            estado=True,
        )
        self.db.add(dia)
        await self.db.flush()
        return dia

    async def list_dias(
        self, id_evento: int, *, for_update: bool = False
    ) -> list[DetalleProgramacionEvento]:
        stmt = (
            select(DetalleProgramacionEvento)
            .join(
                ProgramacionEvento,
                ProgramacionEvento.id_programacion_evento
                == DetalleProgramacionEvento.id_programacion_evento,
            )
            .where(ProgramacionEvento.id_evento == id_evento)
            .order_by(DetalleProgramacionEvento.fecha)
        )
        if for_update:
            stmt = stmt.with_for_update()
        return list((await self.db.scalars(stmt)).all())

    async def get_dia(
        self,
        *,
        id_evento: int,
        id_dia: int,
        for_update: bool = False,
    ) -> DetalleProgramacionEvento | None:
        stmt = (
            select(DetalleProgramacionEvento)
            .join(
                ProgramacionEvento,
                ProgramacionEvento.id_programacion_evento
                == DetalleProgramacionEvento.id_programacion_evento,
            )
            .where(
                ProgramacionEvento.id_evento == id_evento,
                DetalleProgramacionEvento.id_detalle_programacion == id_dia,
            )
        )
        if for_update:
            stmt = stmt.with_for_update()
        return await self.db.scalar(stmt)

    async def update_dia(
        self, dia: DetalleProgramacionEvento, values: dict[str, Any]
    ) -> DetalleProgramacionEvento:
        for field, value in values.items():
            setattr(dia, field, value)
        await self.db.flush()
        return dia

    async def delete_dia(self, dia: DetalleProgramacionEvento) -> None:
        await self.db.delete(dia)

    async def delete_lugar_if_orphan(self, id_lugar: int | None) -> None:
        if id_lugar is None:
            return
        references = await self.db.scalar(
            select(func.count())
            .select_from(ProgramacionEvento)
            .where(ProgramacionEvento.id_lugar == id_lugar)
        )
        if not references:
            lugar = await self.db.get(Lugar, id_lugar)
            if lugar is not None:
                await self.db.delete(lugar)
                await self.db.flush()

    async def delete_evento(self, evento: Evento) -> None:
        await self.db.delete(evento)
        await self.db.flush()

    async def has_participant_dependencies(self, id_evento: int) -> bool:
        participant_table = await self.db.scalar(
            text("SELECT to_regclass('participante')")
        )
        if participant_table is not None:
            participants = await self.db.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM participante "
                    "WHERE id_evento = :id_evento)"
                ),
                {"id_evento": id_evento},
            )
            if participants:
                return True

        table_exists = await self.db.scalar(
            text("SELECT to_regclass('evento_contacto')")
        )
        if table_exists is None:
            return False

        columns = set(
            (
                await self.db.scalars(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = current_schema() "
                        "AND table_name = 'evento_contacto'"
                    )
                )
            ).all()
        )
        column = next(
            (
                candidate
                for candidate in (
                    "id_programacion_evento",
                    "idprogramacionevento",
                )
                if candidate in columns
            ),
            None,
        )
        if column is None:
            return True

        query = text(
            "SELECT EXISTS ("
            "SELECT 1 FROM evento_contacto ec "
            f"JOIN programacion_evento pe ON pe.id_programacion_evento = ec.{column} "
            "WHERE pe.id_evento = :id_evento"
            ")"
        )
        return bool(await self.db.scalar(query, {"id_evento": id_evento}))

    @staticmethod
    def _detalle_select() -> Select[Any]:
        return (
            select(Evento, ProgramacionEvento, Lugar)
            .join(
                ProgramacionEvento,
                ProgramacionEvento.id_evento == Evento.id_evento,
            )
            .outerjoin(Lugar, Lugar.id_lugar == ProgramacionEvento.id_lugar)
        )

    @staticmethod
    def _to_detalle(row: Any) -> EventoDetalle:
        return EventoDetalle(evento=row[0], programacion=row[1], lugar=row[2])

    @staticmethod
    def _list_filters(
        *,
        search: str | None,
        fecha_desde: date | None,
        fecha_hasta: date | None,
        estado: EventoEstado | None,
        modalidad: EventoModalidad | None,
    ) -> list[Any]:
        filters: list[Any] = []
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    Evento.nombre_evento.ilike(pattern),
                    Evento.descripcion.ilike(pattern),
                )
            )
        if fecha_hasta is not None:
            filters.append(Evento.fecha_inicio <= fecha_hasta)
        if fecha_desde is not None:
            filters.append(Evento.fecha_fin >= fecha_desde)
        if estado is not None:
            filters.append(Evento.estado == estado)
        if modalidad is not None:
            filters.append(ProgramacionEvento.modalidad == modalidad)
        return filters
