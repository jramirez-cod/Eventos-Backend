from dataclasses import dataclass
from datetime import date, time
from typing import Any

from sqlalchemy import Select, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.categorias.models import Categoria
from app.modules.eventos.models import (
    DetallePoliticaEvento,
    DetalleProgramacionEvento,
    Evento,
    EventoEstado,
    EventoModalidad,
    Lugar,
    PoliticaEvento,
    ProgramacionEvento,
    ResponsableEvento,
)
from app.modules.maestros.models import Area, Beneficio
from app.modules.participantes.models import EventoEmpresa
from app.modules.usuarios.models import Usuario


@dataclass(frozen=True, slots=True)
class EventoDetalle:
    evento: Evento
    area: Area
    politica: PoliticaEvento
    detalles: list[tuple[DetallePoliticaEvento, Beneficio, Categoria]]


class EventoRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -- Evento -----------------------------------------------------------

    async def get_by_id(self, id_evento: int) -> Evento | None:
        return await self.db.get(Evento, id_evento)

    async def get_by_id_for_update(self, id_evento: int) -> Evento | None:
        stmt = (
            select(Evento).where(Evento.id_evento == id_evento).with_for_update()
        )
        return await self.db.scalar(stmt)

    async def get_area_activa(self, id_area: int) -> Area | None:
        stmt = select(Area).where(Area.id_area == id_area, Area.estado.is_(True))
        return await self.db.scalar(stmt)

    async def get_beneficio_activo(self, id_beneficio: int) -> Beneficio | None:
        stmt = select(Beneficio).where(
            Beneficio.id_beneficio == id_beneficio, Beneficio.estado.is_(True)
        )
        return await self.db.scalar(stmt)

    async def get_categoria_activa(self, id_categoria: int) -> Categoria | None:
        stmt = select(Categoria).where(
            Categoria.id_categoria == id_categoria, Categoria.estado.is_(True)
        )
        return await self.db.scalar(stmt)

    async def get_detallado(self, id_evento: int) -> EventoDetalle | None:
        evento = await self.db.get(Evento, id_evento)
        if evento is None:
            return None
        return await self._build_detalle(evento)

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
        id_area: int | None,
        page: int,
        page_size: int | None,
    ) -> tuple[list[EventoDetalle], int]:
        filters = self._list_filters(
            search=search,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            estado=estado,
            id_area=id_area,
        )
        base = select(Evento).join(
            PoliticaEvento,
            PoliticaEvento.id_politica_evento == Evento.id_politica_evento,
        )
        total = int(
            await self.db.scalar(
                select(func.count()).select_from(base.where(*filters).subquery())
            )
            or 0
        )
        stmt = (
            base.where(*filters)
            .order_by(Evento.id_evento.desc())
            .offset((page - 1) * page_size if page_size else 0)
        )
        if page_size is not None:
            stmt = stmt.limit(page_size)
        eventos = list((await self.db.scalars(stmt)).all())
        detalles = [await self._build_detalle(evento) for evento in eventos]
        return detalles, total

    async def create_politica_evento(
        self, *, fecha_inicio: date, fecha_fin: date
    ) -> PoliticaEvento:
        politica = PoliticaEvento(fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
        self.db.add(politica)
        await self.db.flush()
        return politica

    async def update_politica_evento(
        self, politica: PoliticaEvento, *, fecha_inicio: date, fecha_fin: date
    ) -> PoliticaEvento:
        politica.fecha_inicio = fecha_inicio
        politica.fecha_fin = fecha_fin
        await self.db.flush()
        return politica

    async def create_detalle_politica(
        self,
        *,
        id_politica_evento: int,
        id_beneficio: int,
        id_categoria: int,
        entradas_gratuitas: int,
    ) -> DetallePoliticaEvento:
        detalle = DetallePoliticaEvento(
            id_politica_evento=id_politica_evento,
            id_beneficio=id_beneficio,
            id_categoria=id_categoria,
            entradas_gratuitas=entradas_gratuitas,
        )
        self.db.add(detalle)
        await self.db.flush()
        return detalle

    async def clear_detalles_politica(self, id_politica_evento: int) -> None:
        detalles = list(
            (
                await self.db.scalars(
                    select(DetallePoliticaEvento).where(
                        DetallePoliticaEvento.id_politica_evento
                        == id_politica_evento
                    )
                )
            ).all()
        )
        for detalle in detalles:
            await self.db.delete(detalle)
        await self.db.flush()

    async def create_evento(
        self,
        *,
        nombre_evento: str,
        descripcion: str | None,
        id_politica_evento: int,
        id_area: int,
    ) -> Evento:
        evento = Evento(
            nombre_evento=nombre_evento,
            descripcion=descripcion,
            id_politica_evento=id_politica_evento,
            id_area=id_area,
            estado=EventoEstado.ABIERTO,
        )
        self.db.add(evento)
        await self.db.flush()
        return evento

    async def update_evento(self, evento: Evento, values: dict[str, Any]) -> Evento:
        for field, value in values.items():
            setattr(evento, field, value)
        await self.db.flush()
        return evento

    async def delete_evento(self, evento: Evento) -> None:
        await self.db.delete(evento)
        await self.db.flush()

    # -- Lugar --------------------------------------------------------------

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

    # -- ProgramacionEvento ---------------------------------------------

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
            estado=EventoEstado.ABIERTO,
        )
        self.db.add(programacion)
        await self.db.flush()
        return programacion

    async def get_programacion_by_id(
        self,
        *,
        id_evento: int,
        id_programacion_evento: int,
        for_update: bool = False,
    ) -> ProgramacionEvento | None:
        stmt = select(ProgramacionEvento).where(
            ProgramacionEvento.id_programacion_evento == id_programacion_evento,
            ProgramacionEvento.id_evento == id_evento,
        )
        if for_update:
            stmt = stmt.with_for_update()
        return await self.db.scalar(stmt)

    async def list_programaciones(
        self,
        *,
        id_evento: int,
        fecha_desde: date | None,
        fecha_hasta: date | None,
        modalidad: EventoModalidad | None,
        estado: EventoEstado | None,
        page: int,
        page_size: int,
    ) -> tuple[list[ProgramacionEvento], int]:
        filters: list[Any] = [ProgramacionEvento.id_evento == id_evento]
        if modalidad is not None:
            filters.append(ProgramacionEvento.modalidad == modalidad)
        if estado is not None:
            filters.append(ProgramacionEvento.estado == estado)
        if fecha_desde is not None or fecha_hasta is not None:
            dia_filters = [
                DetalleProgramacionEvento.id_programacion_evento
                == ProgramacionEvento.id_programacion_evento
            ]
            if fecha_desde is not None:
                dia_filters.append(DetalleProgramacionEvento.fecha >= fecha_desde)
            if fecha_hasta is not None:
                dia_filters.append(DetalleProgramacionEvento.fecha <= fecha_hasta)
            filters.append(
                select(DetalleProgramacionEvento.id_detalle_programacion)
                .where(*dia_filters)
                .exists()
            )

        total = int(
            await self.db.scalar(
                select(func.count())
                .select_from(ProgramacionEvento)
                .where(*filters)
            )
            or 0
        )
        stmt = (
            select(ProgramacionEvento)
            .where(*filters)
            .order_by(ProgramacionEvento.id_programacion_evento.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.db.scalars(stmt)).all()), total

    async def list_programaciones_transversal(
        self,
        *,
        fecha_desde: date | None,
        fecha_hasta: date | None,
        id_empresa: int | None,
        estado: EventoEstado | None,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple[ProgramacionEvento, Evento, date | None]], int]:
        filters: list[Any] = []
        if estado is not None:
            filters.append(ProgramacionEvento.estado == estado)
        if fecha_desde is not None or fecha_hasta is not None:
            dia_filters = [
                DetalleProgramacionEvento.id_programacion_evento
                == ProgramacionEvento.id_programacion_evento
            ]
            if fecha_desde is not None:
                dia_filters.append(DetalleProgramacionEvento.fecha >= fecha_desde)
            if fecha_hasta is not None:
                dia_filters.append(DetalleProgramacionEvento.fecha <= fecha_hasta)
            filters.append(
                select(DetalleProgramacionEvento.id_detalle_programacion)
                .where(*dia_filters)
                .exists()
            )
        if id_empresa is not None:
            filters.append(
                select(EventoEmpresa.id_evento_empresa)
                .where(
                    EventoEmpresa.id_programacion_evento
                    == ProgramacionEvento.id_programacion_evento,
                    EventoEmpresa.id_empresa == id_empresa,
                )
                .exists()
            )

        total = int(
            await self.db.scalar(
                select(func.count())
                .select_from(ProgramacionEvento)
                .join(Evento, Evento.id_evento == ProgramacionEvento.id_evento)
                .where(*filters)
            )
            or 0
        )

        primera_fecha_subq = (
            select(func.min(DetalleProgramacionEvento.fecha))
            .where(
                DetalleProgramacionEvento.id_programacion_evento
                == ProgramacionEvento.id_programacion_evento,
                DetalleProgramacionEvento.estado.is_(True),
            )
            .correlate(ProgramacionEvento)
            .scalar_subquery()
        )
        stmt = (
            select(ProgramacionEvento, Evento, primera_fecha_subq)
            .join(Evento, Evento.id_evento == ProgramacionEvento.id_evento)
            .where(*filters)
            .order_by(
                primera_fecha_subq.asc().nulls_last(),
                ProgramacionEvento.id_programacion_evento.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).all()
        return [(row[0], row[1], row[2]) for row in rows], total

    async def update_programacion(
        self, programacion: ProgramacionEvento, values: dict[str, Any]
    ) -> ProgramacionEvento:
        for field, value in values.items():
            setattr(programacion, field, value)
        await self.db.flush()
        return programacion

    async def get_lugar(self, id_lugar: int) -> Lugar | None:
        return await self.db.get(Lugar, id_lugar)

    # -- DetalleProgramacionEvento ("días") -------------------------------

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

    async def get_primera_fecha(self, id_programacion_evento: int) -> date | None:
        stmt = select(func.min(DetalleProgramacionEvento.fecha)).where(
            DetalleProgramacionEvento.id_programacion_evento == id_programacion_evento,
            DetalleProgramacionEvento.estado.is_(True),
        )
        return await self.db.scalar(stmt)

    async def list_dias(
        self, id_programacion_evento: int, *, for_update: bool = False
    ) -> list[DetalleProgramacionEvento]:
        stmt = (
            select(DetalleProgramacionEvento)
            .where(
                DetalleProgramacionEvento.id_programacion_evento
                == id_programacion_evento
            )
            .order_by(DetalleProgramacionEvento.fecha)
        )
        if for_update:
            stmt = stmt.with_for_update()
        return list((await self.db.scalars(stmt)).all())

    async def get_dia(
        self,
        *,
        id_programacion_evento: int,
        id_dia: int,
        for_update: bool = False,
    ) -> DetalleProgramacionEvento | None:
        stmt = select(DetalleProgramacionEvento).where(
            DetalleProgramacionEvento.id_programacion_evento
            == id_programacion_evento,
            DetalleProgramacionEvento.id_detalle_programacion == id_dia,
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
        await self.db.flush()

    async def count_dias(self, id_programacion_evento: int) -> int:
        stmt = (
            select(func.count())
            .select_from(DetalleProgramacionEvento)
            .where(
                DetalleProgramacionEvento.id_programacion_evento
                == id_programacion_evento
            )
        )
        return int(await self.db.scalar(stmt) or 0)

    # -- ResponsableEvento ---------------------------------------------

    async def create_responsable(
        self, *, id_programacion_evento: int, id_usuario: int
    ) -> ResponsableEvento:
        responsable = ResponsableEvento(
            id_programacion_evento=id_programacion_evento,
            id_usuario=id_usuario,
            estado=True,
        )
        self.db.add(responsable)
        await self.db.flush()
        return responsable

    async def get_responsable_by_id(
        self, *, id_programacion_evento: int, id_responsable: int
    ) -> ResponsableEvento | None:
        stmt = select(ResponsableEvento).where(
            ResponsableEvento.id_responsable_evento == id_responsable,
            ResponsableEvento.id_programacion_evento == id_programacion_evento,
        )
        return await self.db.scalar(stmt)

    async def get_responsable_activo(
        self, *, id_programacion_evento: int, id_usuario: int
    ) -> ResponsableEvento | None:
        stmt = select(ResponsableEvento).where(
            ResponsableEvento.id_programacion_evento == id_programacion_evento,
            ResponsableEvento.id_usuario == id_usuario,
            ResponsableEvento.estado.is_(True),
        )
        return await self.db.scalar(stmt)

    async def list_responsables(
        self, id_programacion_evento: int
    ) -> list[tuple[ResponsableEvento, Usuario]]:
        stmt = (
            select(ResponsableEvento, Usuario)
            .join(Usuario, Usuario.id_usuario == ResponsableEvento.id_usuario)
            .where(
                ResponsableEvento.id_programacion_evento == id_programacion_evento
            )
            .order_by(ResponsableEvento.id_responsable_evento)
        )
        rows = (await self.db.execute(stmt)).all()
        return [(row[0], row[1]) for row in rows]

    async def set_responsable_estado(
        self, responsable: ResponsableEvento, *, estado: bool
    ) -> ResponsableEvento:
        responsable.estado = estado
        await self.db.flush()
        return responsable

    # -- Dependencias para borrado ---------------------------------------

    async def has_evento_contacto_dependencies(self, id_evento: int) -> bool:
        table_exists = await self.db.scalar(
            text("SELECT to_regclass('evento_contacto')")
        )
        if table_exists is None:
            return False
        query = text(
            "SELECT EXISTS ("
            "SELECT 1 FROM evento_contacto ec "
            "JOIN programacion_evento pe "
            "ON pe.id_programacion_evento = ec.id_programacion_evento "
            "WHERE pe.id_evento = :id_evento"
            ")"
        )
        return bool(await self.db.scalar(query, {"id_evento": id_evento}))

    # -- helpers internos -------------------------------------------------

    async def _build_detalle(self, evento: Evento) -> EventoDetalle:
        area = await self.db.get(Area, evento.id_area)
        assert area is not None
        politica = await self.db.get(PoliticaEvento, evento.id_politica_evento)
        assert politica is not None
        stmt = (
            select(DetallePoliticaEvento, Beneficio, Categoria)
            .join(
                Beneficio,
                Beneficio.id_beneficio == DetallePoliticaEvento.id_beneficio,
            )
            .join(
                Categoria,
                Categoria.id_categoria == DetallePoliticaEvento.id_categoria,
            )
            .where(
                DetallePoliticaEvento.id_politica_evento
                == politica.id_politica_evento
            )
            .order_by(DetallePoliticaEvento.id_detalle_politica_evento)
        )
        rows = (await self.db.execute(stmt)).all()
        detalles = [(row[0], row[1], row[2]) for row in rows]
        return EventoDetalle(
            evento=evento, area=area, politica=politica, detalles=detalles
        )

    @staticmethod
    def _list_filters(
        *,
        search: str | None,
        fecha_desde: date | None,
        fecha_hasta: date | None,
        estado: EventoEstado | None,
        id_area: int | None,
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
            filters.append(PoliticaEvento.fecha_inicio <= fecha_hasta)
        if fecha_desde is not None:
            filters.append(PoliticaEvento.fecha_fin >= fecha_desde)
        if estado is not None:
            filters.append(Evento.estado == estado)
        if id_area is not None:
            filters.append(Evento.id_area == id_area)
        return filters
