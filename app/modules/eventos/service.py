from datetime import date, datetime
from io import BytesIO
import math
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo

from anyio import to_thread
from fastapi import UploadFile
from openpyxl import Workbook
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.auditoria.repository import AuditoriaRepository
from app.modules.eventos.dto import (
    DetalleProgramacionResponse,
    DetalleProgramacionUpdate,
    DetallePoliticaEventoResponse,
    EventoCreate,
    EventoListItem,
    EventoListResponse,
    EventoResponse,
    EventoUpdate,
    LugarCreate,
    LugarResponse,
    PoliticaEventoCreate,
    PoliticaEventoResponse,
    PoliticaEventoUpdate,
    ProgramacionDiaCreate,
    ProgramacionEventoCreate,
    ProgramacionEventoListResponse,
    ProgramacionEventoResponse,
    ProgramacionEventoTransversalListResponse,
    ProgramacionEventoTransversalResponse,
    ProgramacionEventoUpdate,
    ResponsableEventoCreate,
    ResponsableEventoResponse,
)
from app.modules.eventos.models import (
    DetalleProgramacionEvento,
    Evento,
    EventoEstado,
    EventoModalidad,
    Lugar,
    PoliticaEvento,
    ProgramacionEvento,
)
from app.modules.eventos.repository import EventoDetalle, EventoRepository
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.repository import UsuarioRepository


MODULO_EVENTOS = "EVENTOS"
PERU_TIMEZONE = ZoneInfo("America/Lima")
FLYER_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


class EventoServiceError(Exception):
    pass


class EventoNotFoundError(EventoServiceError):
    pass


class AreaNotFoundError(EventoServiceError):
    pass


class BeneficioNotFoundError(EventoServiceError):
    pass


class CategoriaNotFoundError(EventoServiceError):
    pass


class ProgramacionNotFoundError(EventoServiceError):
    pass


class DiaNotFoundError(EventoServiceError):
    pass


class UltimoDiaNoEliminableError(EventoServiceError):
    pass


class ResponsableNotFoundError(EventoServiceError):
    pass


class ResponsableDuplicadoError(EventoServiceError):
    pass


class InvalidDateRangeError(EventoServiceError):
    pass


class InvalidScheduleError(EventoServiceError):
    pass


class LugarRequeridoError(EventoServiceError):
    pass


class LugarNoPermitidoError(EventoServiceError):
    pass


class InvalidStateTransitionError(EventoServiceError):
    pass


class EventoNotEditableError(EventoServiceError):
    pass


class ProgramacionNotEditableError(EventoServiceError):
    pass


class EventoDependencyError(EventoServiceError):
    pass


class EventoPersistenceConflictError(EventoServiceError):
    pass


class InvalidFlyerError(EventoServiceError):
    pass


class FlyerTooLargeError(EventoServiceError):
    pass


class FlyerNotFoundError(EventoServiceError):
    pass


class EventoService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.eventos = EventoRepository(db)
        self.usuarios = UsuarioRepository(db)
        self.auditoria = AuditoriaRepository(db)

    # -- Evento -------------------------------------------------------

    async def crear_evento(
        self, *, data: EventoCreate, actor: Usuario
    ) -> EventoResponse:
        nombre = self._normalize_required(data.nombre_evento, "nombre del evento")
        nombre_repetido = await self.eventos.count_by_name(nombre) > 0
        if await self.eventos.get_area_activa(data.id_area) is None:
            raise AreaNotFoundError("El área indicada no existe o está inactiva.")
        await self._validate_politica(data.politica)

        try:
            politica = await self.eventos.create_politica_evento(
                fecha_inicio=data.politica.fecha_inicio,
                fecha_fin=data.politica.fecha_fin,
            )
            for detalle in data.politica.detalles:
                await self.eventos.create_detalle_politica(
                    id_politica_evento=politica.id_politica_evento,
                    id_beneficio=detalle.id_beneficio,
                    id_categoria=detalle.id_categoria,
                    entradas_gratuitas=detalle.entradas_gratuitas,
                )
            evento = await self.eventos.create_evento(
                nombre_evento=nombre,
                descripcion=self._normalize_optional(data.descripcion),
                id_politica_evento=politica.id_politica_evento,
                id_area=data.id_area,
            )
            audit_values = {"id_evento": evento.id_evento, "nombre_evento": nombre}
            if nombre_repetido:
                audit_values["advertencia_nombre_repetido"] = True
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento",
                id_entidad=evento.id_evento,
                accion="CREAR_EVENTO",
                valor_nuevo=audit_values,
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise EventoPersistenceConflictError(
                "No se pudo crear el evento por un conflicto de integridad."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

        return await self.obtener_evento(evento.id_evento)

    async def obtener_evento(self, id_evento: int) -> EventoResponse:
        detalle = await self.eventos.get_detallado(id_evento)
        if detalle is None:
            raise EventoNotFoundError("Evento no encontrado.")
        return self._to_response(detalle)

    async def listar_eventos(
        self,
        *,
        search: str | None,
        fecha_desde: date | None,
        fecha_hasta: date | None,
        estado: EventoEstado | None,
        id_area: int | None,
        page: int,
        page_size: int,
    ) -> EventoListResponse:
        self._validate_filter_dates(fecha_desde, fecha_hasta)
        rows, total = await self.eventos.list_detallado(
            search=search,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            estado=estado,
            id_area=id_area,
            page=page,
            page_size=page_size,
        )
        return EventoListResponse(
            items=[
                EventoListItem(**self._to_response(row).model_dump()) for row in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def actualizar_evento(
        self, *, id_evento: int, data: EventoUpdate, actor: Usuario
    ) -> EventoResponse:
        evento = await self._get_evento_for_update(id_evento)
        self.validar_evento_abierto(evento)
        values = data.model_dump(exclude_unset=True)
        if "nombre_evento" in values:
            values["nombre_evento"] = self._normalize_required(
                values["nombre_evento"], "nombre del evento"
            )
        if "descripcion" in values:
            values["descripcion"] = self._normalize_optional(values["descripcion"])
        if "id_area" in values:
            if await self.eventos.get_area_activa(values["id_area"]) is None:
                raise AreaNotFoundError("El área indicada no existe o está inactiva.")

        anterior = self._evento_values(evento)
        try:
            await self.eventos.update_evento(evento, values)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento",
                id_entidad=id_evento,
                accion="ACTUALIZAR_EVENTO",
                valor_anterior=anterior,
                valor_nuevo=self._evento_values(evento),
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise EventoPersistenceConflictError(
                "No se pudo actualizar el evento por un conflicto de integridad."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise
        return await self.obtener_evento(id_evento)

    # -- Política de evento -----------------------------------------------

    async def actualizar_politica(
        self, *, id_evento: int, data: PoliticaEventoUpdate, actor: Usuario
    ) -> EventoResponse:
        evento = await self._get_evento_for_update(id_evento)
        self.validar_evento_abierto(evento)
        await self._validate_politica(data)
        politica = await self.db.get(PoliticaEvento, evento.id_politica_evento)
        assert politica is not None
        anterior = {
            "fecha_inicio": politica.fecha_inicio.isoformat(),
            "fecha_fin": politica.fecha_fin.isoformat(),
        }
        try:
            await self.eventos.update_politica_evento(
                politica,
                fecha_inicio=data.fecha_inicio,
                fecha_fin=data.fecha_fin,
            )
            await self.eventos.clear_detalles_politica(politica.id_politica_evento)
            for detalle in data.detalles:
                await self.eventos.create_detalle_politica(
                    id_politica_evento=politica.id_politica_evento,
                    id_beneficio=detalle.id_beneficio,
                    id_categoria=detalle.id_categoria,
                    entradas_gratuitas=detalle.entradas_gratuitas,
                )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento",
                id_entidad=id_evento,
                accion="ACTUALIZAR_POLITICA_EVENTO",
                valor_anterior=anterior,
                valor_nuevo={
                    "fecha_inicio": data.fecha_inicio.isoformat(),
                    "fecha_fin": data.fecha_fin.isoformat(),
                },
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return await self.obtener_evento(id_evento)

    # -- ProgramacionEvento -------------------------------------------

    async def crear_programacion(
        self, *, id_evento: int, data: ProgramacionEventoCreate, actor: Usuario
    ) -> ProgramacionEventoResponse:
        evento = await self._get_evento_for_update(id_evento)
        self.validar_evento_abierto(evento)

        try:
            lugar = await self._create_lugar(data.lugar)
            programacion = await self.eventos.create_programacion(
                id_evento=id_evento,
                id_lugar=lugar.id_lugar if lugar else None,
                modalidad=data.modalidad,
                enlace_general=self._normalize_optional(data.enlace_general),
            )
            for dia in data.dias:
                await self.eventos.create_dia(
                    id_programacion_evento=programacion.id_programacion_evento,
                    fecha=dia.fecha,
                    hora_inicio=dia.hora_inicio,
                    hora_fin=dia.hora_fin,
                    enlace=self._normalize_optional(dia.enlace),
                )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento",
                id_entidad=id_evento,
                accion="CREAR_PROGRAMACION_EVENTO",
                valor_nuevo=self._programacion_values(programacion, lugar),
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise EventoPersistenceConflictError(
                "No se pudo crear la programación por un conflicto de integridad."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise
        return await self.obtener_programacion(
            id_evento=id_evento, id_programacion=programacion.id_programacion_evento
        )

    async def obtener_programacion(
        self, *, id_evento: int, id_programacion: int
    ) -> ProgramacionEventoResponse:
        programacion = await self.eventos.get_programacion_by_id(
            id_evento=id_evento, id_programacion_evento=id_programacion
        )
        if programacion is None:
            raise ProgramacionNotFoundError("Programación no encontrada.")
        lugar = (
            await self.eventos.get_lugar(programacion.id_lugar)
            if programacion.id_lugar is not None
            else None
        )
        primera_fecha = await self.eventos.get_primera_fecha(
            programacion.id_programacion_evento
        )
        return self._programacion_response(programacion, lugar, primera_fecha)

    async def listar_programaciones(
        self,
        *,
        id_evento: int,
        fecha_desde: date | None,
        fecha_hasta: date | None,
        modalidad: EventoModalidad | None,
        estado: EventoEstado | None,
        page: int,
        page_size: int,
    ) -> ProgramacionEventoListResponse:
        if await self.eventos.get_by_id(id_evento) is None:
            raise EventoNotFoundError("Evento no encontrado.")
        self._validate_filter_dates(fecha_desde, fecha_hasta)
        rows, total = await self.eventos.list_programaciones(
            id_evento=id_evento,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            modalidad=modalidad,
            estado=estado,
            page=page,
            page_size=page_size,
        )
        items = []
        for programacion in rows:
            lugar = (
                await self.eventos.get_lugar(programacion.id_lugar)
                if programacion.id_lugar is not None
                else None
            )
            primera_fecha = await self.eventos.get_primera_fecha(
                programacion.id_programacion_evento
            )
            items.append(
                self._programacion_response(programacion, lugar, primera_fecha)
            )
        return ProgramacionEventoListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def listar_programaciones_transversal(
        self,
        *,
        fecha_desde: date | None,
        fecha_hasta: date | None,
        id_empresa: int | None,
        estado: EventoEstado | None,
        page: int,
        page_size: int,
    ) -> ProgramacionEventoTransversalListResponse:
        self._validate_filter_dates(fecha_desde, fecha_hasta)
        rows, total = await self.eventos.list_programaciones_transversal(
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            id_empresa=id_empresa,
            estado=estado,
            page=page,
            page_size=page_size,
        )
        items = []
        for programacion, evento, primera_fecha in rows:
            lugar = (
                await self.eventos.get_lugar(programacion.id_lugar)
                if programacion.id_lugar is not None
                else None
            )
            items.append(
                ProgramacionEventoTransversalResponse(
                    **self._programacion_response(
                        programacion, lugar, primera_fecha
                    ).model_dump(),
                    nombre_evento=evento.nombre_evento,
                )
            )
        return ProgramacionEventoTransversalListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def actualizar_programacion(
        self,
        *,
        id_evento: int,
        id_programacion: int,
        data: ProgramacionEventoUpdate,
        actor: Usuario,
    ) -> ProgramacionEventoResponse:
        evento = await self._get_evento_for_update(id_evento)
        self.validar_evento_abierto(evento)
        programacion = await self.eventos.get_programacion_by_id(
            id_evento=id_evento,
            id_programacion_evento=id_programacion,
            for_update=True,
        )
        if programacion is None:
            raise ProgramacionNotFoundError("Programación no encontrada.")
        self.validar_programacion_abierta(programacion)
        lugar_actual = (
            await self.eventos.get_lugar(programacion.id_lugar)
            if programacion.id_lugar is not None
            else None
        )
        anterior = self._programacion_values(programacion, lugar_actual)

        modalidad_efectiva = (
            data.modalidad if data.modalidad is not None else programacion.modalidad
        )
        tendra_lugar = (
            data.lugar is not None
            if "lugar" in data.model_fields_set
            else lugar_actual is not None
        )
        if (
            modalidad_efectiva in (EventoModalidad.PRESENCIAL, EventoModalidad.HIBRIDO)
            and not tendra_lugar
        ):
            raise LugarRequeridoError(
                "Debe especificar un lugar para programaciones presenciales o híbridas."
            )
        if modalidad_efectiva == EventoModalidad.VIRTUAL and tendra_lugar:
            raise LugarNoPermitidoError(
                "Las programaciones virtuales no admiten un lugar físico."
            )

        values = data.model_dump(exclude_unset=True, exclude={"lugar"})
        if "enlace_general" in values:
            values["enlace_general"] = self._normalize_optional(
                values["enlace_general"]
            )
        old_lugar_id = programacion.id_lugar

        try:
            nuevo_lugar = lugar_actual
            if "lugar" in data.model_fields_set:
                if data.lugar is None:
                    nuevo_lugar = None
                    values["id_lugar"] = None
                elif lugar_actual is None:
                    nuevo_lugar = await self._create_lugar(data.lugar)
                    values["id_lugar"] = nuevo_lugar.id_lugar
                else:
                    await self.eventos.update_lugar(
                        lugar_actual, data.lugar.model_dump(exclude_unset=True)
                    )
            await self.eventos.update_programacion(programacion, values)
            if old_lugar_id != programacion.id_lugar:
                await self.eventos.delete_lugar_if_orphan(old_lugar_id)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento",
                id_entidad=id_evento,
                accion="ACTUALIZAR_PROGRAMACION_EVENTO",
                valor_anterior=anterior,
                valor_nuevo=self._programacion_values(programacion, nuevo_lugar),
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return await self.obtener_programacion(
            id_evento=id_evento, id_programacion=id_programacion
        )

    # -- Días de la programación ---------------------------------------

    async def listar_dias(
        self, *, id_evento: int, id_programacion: int
    ) -> list[DetalleProgramacionResponse]:
        if (
            await self.eventos.get_programacion_by_id(
                id_evento=id_evento, id_programacion_evento=id_programacion
            )
            is None
        ):
            raise ProgramacionNotFoundError("Programación no encontrada.")
        dias = await self.eventos.list_dias(id_programacion)
        return [DetalleProgramacionResponse.model_validate(dia) for dia in dias]

    async def crear_dia(
        self,
        *,
        id_evento: int,
        id_programacion: int,
        data: ProgramacionDiaCreate,
        actor: Usuario,
    ) -> DetalleProgramacionResponse:
        evento = await self._get_evento_for_update(id_evento)
        self.validar_evento_abierto(evento)
        programacion = await self.eventos.get_programacion_by_id(
            id_evento=id_evento,
            id_programacion_evento=id_programacion,
            for_update=True,
        )
        if programacion is None:
            raise ProgramacionNotFoundError("Programación no encontrada.")
        self.validar_programacion_abierta(programacion)
        try:
            dia = await self.eventos.create_dia(
                id_programacion_evento=id_programacion,
                fecha=data.fecha,
                hora_inicio=data.hora_inicio,
                hora_fin=data.hora_fin,
                enlace=self._normalize_optional(data.enlace),
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento",
                id_entidad=id_evento,
                accion="CREAR_DIA_EVENTO",
                valor_nuevo=self._dia_values(dia),
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise EventoPersistenceConflictError(
                "Ya existe un día con esa fecha en la programación."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise
        return DetalleProgramacionResponse.model_validate(dia)

    async def actualizar_dia(
        self,
        *,
        id_evento: int,
        id_programacion: int,
        id_dia: int,
        data: DetalleProgramacionUpdate,
        actor: Usuario,
    ) -> DetalleProgramacionResponse:
        evento = await self._get_evento_for_update(id_evento)
        self.validar_evento_abierto(evento)
        programacion = await self.eventos.get_programacion_by_id(
            id_evento=id_evento, id_programacion_evento=id_programacion, for_update=True
        )
        if programacion is None:
            raise ProgramacionNotFoundError("Programación no encontrada.")
        self.validar_programacion_abierta(programacion)
        dia = await self.eventos.get_dia(
            id_programacion_evento=id_programacion, id_dia=id_dia, for_update=True
        )
        if dia is None:
            raise DiaNotFoundError("Día del evento no encontrado.")
        values = data.model_dump(exclude_unset=True)
        if "enlace" in values:
            values["enlace"] = self._normalize_optional(values["enlace"])
        hora_inicio = values.get("hora_inicio", dia.hora_inicio)
        hora_fin = values.get("hora_fin", dia.hora_fin)
        self._validate_schedule(hora_inicio, hora_fin)
        anterior = self._dia_values(dia)

        try:
            await self.eventos.update_dia(dia, values)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento",
                id_entidad=id_evento,
                accion="ACTUALIZAR_DIA_EVENTO",
                valor_anterior=anterior,
                valor_nuevo=self._dia_values(dia),
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise EventoPersistenceConflictError(
                "No se pudo actualizar el día del evento."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise
        return DetalleProgramacionResponse.model_validate(dia)

    async def eliminar_dia(
        self, *, id_evento: int, id_programacion: int, id_dia: int, actor: Usuario
    ) -> None:
        evento = await self._get_evento_for_update(id_evento)
        self.validar_evento_abierto(evento)
        programacion = await self.eventos.get_programacion_by_id(
            id_evento=id_evento, id_programacion_evento=id_programacion, for_update=True
        )
        if programacion is None:
            raise ProgramacionNotFoundError("Programación no encontrada.")
        self.validar_programacion_abierta(programacion)
        dia = await self.eventos.get_dia(
            id_programacion_evento=id_programacion, id_dia=id_dia, for_update=True
        )
        if dia is None:
            raise DiaNotFoundError("Día del evento no encontrado.")
        if await self.eventos.count_dias(id_programacion) <= 1:
            raise UltimoDiaNoEliminableError(
                "La programación debe tener al menos un día."
            )
        try:
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento",
                id_entidad=id_evento,
                accion="ELIMINAR_DIA_EVENTO",
                valor_anterior=self._dia_values(dia),
                valor_nuevo=None,
            )
            await self.eventos.delete_dia(dia)
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

    # -- Responsables de la programación ------------------------------

    async def crear_responsable(
        self,
        *,
        id_evento: int,
        id_programacion: int,
        data: ResponsableEventoCreate,
        actor: Usuario,
    ) -> ResponsableEventoResponse:
        evento = await self._get_evento_for_update(id_evento)
        self.validar_evento_abierto(evento)
        programacion = await self.eventos.get_programacion_by_id(
            id_evento=id_evento, id_programacion_evento=id_programacion, for_update=True
        )
        if programacion is None:
            raise ProgramacionNotFoundError("Programación no encontrada.")
        self.validar_programacion_abierta(programacion)
        usuario = await self.usuarios.get_by_id(data.id_usuario)
        if usuario is None:
            raise EventoServiceError("El usuario indicado no existe.")
        if (
            await self.eventos.get_responsable_activo(
                id_programacion_evento=id_programacion, id_usuario=data.id_usuario
            )
            is not None
        ):
            raise ResponsableDuplicadoError(
                "El usuario ya es responsable de esta programación."
            )
        try:
            responsable = await self.eventos.create_responsable(
                id_programacion_evento=id_programacion, id_usuario=data.id_usuario
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento",
                id_entidad=id_evento,
                accion="ASIGNAR_RESPONSABLE_EVENTO",
                valor_nuevo={
                    "id_responsable_evento": responsable.id_responsable_evento,
                    "id_usuario": data.id_usuario,
                },
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ResponsableDuplicadoError(
                "El usuario ya es responsable de esta programación."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise
        return ResponsableEventoResponse(
            id_responsable_evento=responsable.id_responsable_evento,
            id_programacion_evento=responsable.id_programacion_evento,
            id_usuario=usuario.id_usuario,
            nombre_usuario=usuario.nombre_usuario,
            estado=responsable.estado,
        )

    async def listar_responsables(
        self, *, id_evento: int, id_programacion: int
    ) -> list[ResponsableEventoResponse]:
        if (
            await self.eventos.get_programacion_by_id(
                id_evento=id_evento, id_programacion_evento=id_programacion
            )
            is None
        ):
            raise ProgramacionNotFoundError("Programación no encontrada.")
        rows = await self.eventos.list_responsables(id_programacion)
        return [
            ResponsableEventoResponse(
                id_responsable_evento=responsable.id_responsable_evento,
                id_programacion_evento=responsable.id_programacion_evento,
                id_usuario=usuario.id_usuario,
                nombre_usuario=usuario.nombre_usuario,
                estado=responsable.estado,
            )
            for responsable, usuario in rows
        ]

    async def cambiar_estado_responsable(
        self,
        *,
        id_evento: int,
        id_programacion: int,
        id_responsable: int,
        estado: bool,
        actor: Usuario,
    ) -> ResponsableEventoResponse:
        evento = await self._get_evento_for_update(id_evento)
        self.validar_evento_abierto(evento)
        programacion = await self.eventos.get_programacion_by_id(
            id_evento=id_evento, id_programacion_evento=id_programacion, for_update=True
        )
        if programacion is None:
            raise ProgramacionNotFoundError("Programación no encontrada.")
        self.validar_programacion_abierta(programacion)
        responsable = await self.eventos.get_responsable_by_id(
            id_programacion_evento=id_programacion, id_responsable=id_responsable
        )
        if responsable is None:
            raise ResponsableNotFoundError("Responsable no encontrado.")
        usuario = await self.usuarios.get_by_id(responsable.id_usuario)
        assert usuario is not None
        try:
            await self.eventos.set_responsable_estado(responsable, estado=estado)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento",
                id_entidad=id_evento,
                accion=(
                    "REACTIVAR_RESPONSABLE_EVENTO"
                    if estado
                    else "DESACTIVAR_RESPONSABLE_EVENTO"
                ),
                valor_nuevo={"estado": estado},
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return ResponsableEventoResponse(
            id_responsable_evento=responsable.id_responsable_evento,
            id_programacion_evento=responsable.id_programacion_evento,
            id_usuario=usuario.id_usuario,
            nombre_usuario=usuario.nombre_usuario,
            estado=responsable.estado,
        )

    # -- Flyer ----------------------------------------------------------

    async def subir_flyer(
        self, *, id_evento: int, flyer: UploadFile, actor: Usuario
    ) -> EventoResponse:
        evento = await self._get_evento_for_update(id_evento)
        self.validar_evento_abierto(evento)
        extension = Path(flyer.filename or "").suffix.lower()
        expected_type = FLYER_CONTENT_TYPES.get(extension)
        if expected_type is None or flyer.content_type != expected_type:
            raise InvalidFlyerError("El flyer debe ser JPG, JPEG o PNG.")

        content = await flyer.read(settings.event_flyer_max_bytes + 1)
        if len(content) > settings.event_flyer_max_bytes:
            raise FlyerTooLargeError(
                f"El flyer no debe superar {settings.event_flyer_max_bytes} bytes."
            )
        if not content:
            raise InvalidFlyerError("El archivo del flyer está vacío.")

        filename = f"{uuid4().hex}{extension}"
        new_path = self._flyer_root() / filename
        old_url = evento.flyer_url
        new_url = f"/api/v1/eventos/flyers/{filename}"
        await to_thread.run_sync(self._write_atomic, new_path, content)

        try:
            evento.flyer_url = new_url
            await self.db.flush()
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento",
                id_entidad=id_evento,
                accion=(
                    "REEMPLAZAR_FLYER_EVENTO" if old_url else "ADJUNTAR_FLYER_EVENTO"
                ),
                valor_anterior={"flyer_url": old_url},
                valor_nuevo={"flyer_url": new_url},
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            await to_thread.run_sync(self._unlink_if_exists, new_path)
            raise

        if old_url:
            await to_thread.run_sync(
                self._unlink_if_exists, self._path_from_flyer_url(old_url)
            )
        return await self.obtener_evento(id_evento)

    def obtener_ruta_flyer(self, filename: str) -> Path:
        if Path(filename).name != filename:
            raise FlyerNotFoundError("Flyer no encontrado.")
        path = (self._flyer_root() / filename).resolve()
        if path.parent != self._flyer_root() or not path.is_file():
            raise FlyerNotFoundError("Flyer no encontrado.")
        return path

    # -- Estados ----------------------------------------------------------

    async def finalizar_evento(
        self, *, id_evento: int, motivo: str | None, actor: Usuario
    ) -> EventoResponse:
        return await self._change_state(
            id_evento=id_evento,
            expected=EventoEstado.ABIERTO,
            target=EventoEstado.FINALIZADO,
            action="FINALIZAR_EVENTO",
            motivo=motivo,
            actor=actor,
        )

    async def reabrir_evento(
        self, *, id_evento: int, motivo: str, actor: Usuario
    ) -> EventoResponse:
        return await self._change_state(
            id_evento=id_evento,
            expected=EventoEstado.FINALIZADO,
            target=EventoEstado.ABIERTO,
            action="REABRIR_EVENTO",
            motivo=motivo,
            actor=actor,
        )

    async def inactivar_evento(
        self, *, id_evento: int, motivo: str | None, actor: Usuario
    ) -> EventoResponse:
        evento = await self._get_evento_for_update(id_evento)
        if evento.estado == EventoEstado.INACTIVO:
            raise InvalidStateTransitionError("El evento ya está inactivo.")
        anterior = evento.estado
        try:
            evento.estado = EventoEstado.INACTIVO
            await self.db.flush()
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento",
                id_entidad=id_evento,
                accion="INACTIVAR_EVENTO",
                valor_anterior={"estado": anterior.value},
                valor_nuevo={"estado": EventoEstado.INACTIVO.value},
                motivo=motivo,
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return await self.obtener_evento(id_evento)

    async def finalizar_programacion(
        self, *, id_evento: int, id_programacion: int, motivo: str | None, actor: Usuario
    ) -> ProgramacionEventoResponse:
        return await self._change_state_programacion(
            id_evento=id_evento,
            id_programacion=id_programacion,
            expected=EventoEstado.ABIERTO,
            target=EventoEstado.FINALIZADO,
            action="FINALIZAR_PROGRAMACION",
            motivo=motivo,
            actor=actor,
        )

    async def reabrir_programacion(
        self, *, id_evento: int, id_programacion: int, motivo: str, actor: Usuario
    ) -> ProgramacionEventoResponse:
        return await self._change_state_programacion(
            id_evento=id_evento,
            id_programacion=id_programacion,
            expected=EventoEstado.FINALIZADO,
            target=EventoEstado.ABIERTO,
            action="REABRIR_PROGRAMACION",
            motivo=motivo,
            actor=actor,
        )

    async def inactivar_programacion(
        self, *, id_evento: int, id_programacion: int, motivo: str | None, actor: Usuario
    ) -> ProgramacionEventoResponse:
        evento = await self._get_evento_for_update(id_evento)
        self.validar_evento_abierto(evento)
        programacion = await self.eventos.get_programacion_by_id(
            id_evento=id_evento, id_programacion_evento=id_programacion, for_update=True
        )
        if programacion is None:
            raise ProgramacionNotFoundError("Programación no encontrada.")
        if programacion.estado == EventoEstado.INACTIVO:
            raise InvalidStateTransitionError("La programación ya está inactiva.")
        anterior = programacion.estado
        try:
            programacion.estado = EventoEstado.INACTIVO
            await self.db.flush()
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="programacion_evento",
                id_entidad=id_programacion,
                accion="INACTIVAR_PROGRAMACION",
                valor_anterior={"estado": anterior.value},
                valor_nuevo={"estado": EventoEstado.INACTIVO.value},
                motivo=motivo,
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return await self.obtener_programacion(
            id_evento=id_evento, id_programacion=id_programacion
        )

    async def eliminar_evento(self, *, id_evento: int, actor: Usuario) -> None:
        evento = await self._get_evento_for_update(id_evento)
        if await self.eventos.has_evento_contacto_dependencies(id_evento):
            raise EventoDependencyError(
                "No se puede eliminar el evento porque tiene contactos asociados."
            )
        detalle = await self.eventos.get_detallado(id_evento)
        old_flyer_url = evento.flyer_url
        id_politica_evento = evento.id_politica_evento

        try:
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento",
                id_entidad=id_evento,
                accion="ELIMINAR_EVENTO",
                valor_anterior=self._evento_values(evento),
                valor_nuevo=None,
            )
            await self.eventos.delete_evento(evento)
            if detalle is not None:
                await self.eventos.clear_detalles_politica(id_politica_evento)
                politica = await self.db.get(
                    type(detalle.politica), id_politica_evento
                )
                if politica is not None:
                    await self.db.delete(politica)
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise EventoDependencyError(
                "No se puede eliminar el evento porque tiene relaciones dependientes."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

        if old_flyer_url:
            await to_thread.run_sync(
                self._unlink_if_exists, self._path_from_flyer_url(old_flyer_url)
            )

    async def exportar_eventos(
        self,
        *,
        search: str | None,
        fecha_desde: date | None,
        fecha_hasta: date | None,
        estado: EventoEstado | None,
        id_area: int | None,
    ) -> bytes:
        self._validate_filter_dates(fecha_desde, fecha_hasta)
        rows, _ = await self.eventos.list_detallado(
            search=search,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            estado=estado,
            id_area=id_area,
            page=1,
            page_size=None,
        )
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Eventos"
        sheet.append(
            [
                "ID",
                "Nombre",
                "Descripción",
                "Área",
                "Política: Fecha inicio",
                "Política: Fecha fin",
                "Estado",
            ]
        )
        for row in rows:
            sheet.append(
                [
                    row.evento.id_evento,
                    row.evento.nombre_evento,
                    row.evento.descripcion or "",
                    row.area.nombre_area,
                    row.politica.fecha_inicio,
                    row.politica.fecha_fin,
                    row.evento.estado.value,
                ]
            )
        output = BytesIO()
        workbook.save(output)
        workbook.close()
        return output.getvalue()

    async def _change_state(
        self,
        *,
        id_evento: int,
        expected: EventoEstado,
        target: EventoEstado,
        action: str,
        motivo: str | None,
        actor: Usuario,
    ) -> EventoResponse:
        evento = await self._get_evento_for_update(id_evento)
        if evento.estado != expected:
            raise InvalidStateTransitionError(
                f"El evento debe estar {expected.value} para ejecutar esta operación."
            )
        try:
            evento.estado = target
            await self.db.flush()
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento",
                id_entidad=id_evento,
                accion=action,
                valor_anterior={"estado": expected.value},
                valor_nuevo={"estado": target.value},
                motivo=motivo,
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return await self.obtener_evento(id_evento)

    async def _change_state_programacion(
        self,
        *,
        id_evento: int,
        id_programacion: int,
        expected: EventoEstado,
        target: EventoEstado,
        action: str,
        motivo: str | None,
        actor: Usuario,
    ) -> ProgramacionEventoResponse:
        evento = await self._get_evento_for_update(id_evento)
        self.validar_evento_abierto(evento)
        programacion = await self.eventos.get_programacion_by_id(
            id_evento=id_evento, id_programacion_evento=id_programacion, for_update=True
        )
        if programacion is None:
            raise ProgramacionNotFoundError("Programación no encontrada.")
        if programacion.estado != expected:
            raise InvalidStateTransitionError(
                f"La programación debe estar {expected.value} para ejecutar esta operación."
            )
        try:
            programacion.estado = target
            await self.db.flush()
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="programacion_evento",
                id_entidad=id_programacion,
                accion=action,
                valor_anterior={"estado": expected.value},
                valor_nuevo={"estado": target.value},
                motivo=motivo,
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return await self.obtener_programacion(
            id_evento=id_evento, id_programacion=id_programacion
        )

    async def _get_evento_for_update(self, id_evento: int) -> Evento:
        evento = await self.eventos.get_by_id_for_update(id_evento)
        if evento is None:
            raise EventoNotFoundError("Evento no encontrado.")
        return evento

    async def _create_lugar(self, data: LugarCreate | None) -> Lugar | None:
        if data is None:
            return None
        return await self.eventos.create_lugar(**data.model_dump())

    async def _validate_politica(
        self, politica: PoliticaEventoCreate | PoliticaEventoUpdate
    ) -> None:
        self._validate_date_range(politica.fecha_inicio, politica.fecha_fin)
        for detalle in politica.detalles:
            beneficio = await self.eventos.get_beneficio_activo(detalle.id_beneficio)
            if beneficio is None:
                raise BeneficioNotFoundError(
                    "El beneficio indicado no existe o está inactivo."
                )
            if await self.eventos.get_categoria_activa(detalle.id_categoria) is None:
                raise CategoriaNotFoundError(
                    "La categoría indicada no existe o está inactiva."
                )

    async def _id_modulo(self) -> int | None:
        modulo = await self.usuarios.get_module_by_name(MODULO_EVENTOS)
        return modulo.id_modulo if modulo else None

    @staticmethod
    def validar_evento_abierto(evento: Evento) -> None:
        if evento.estado != EventoEstado.ABIERTO:
            raise EventoNotEditableError(
                "Solo los eventos abiertos pueden modificarse."
            )

    @staticmethod
    def validar_programacion_abierta(programacion: ProgramacionEvento) -> None:
        if programacion.estado != EventoEstado.ABIERTO:
            raise ProgramacionNotEditableError(
                "Solo las programaciones abiertas pueden modificarse."
            )

    @staticmethod
    def _validate_date_range(fecha_inicio: date, fecha_fin: date) -> None:
        today = datetime.now(PERU_TIMEZONE).date()
        if fecha_inicio < today:
            raise InvalidDateRangeError(
                "La fecha de inicio no puede estar en el pasado."
            )
        if fecha_fin < fecha_inicio:
            raise InvalidDateRangeError(
                "La fecha final no puede ser anterior a la fecha inicial."
            )

    @staticmethod
    def _validate_filter_dates(
        fecha_desde: date | None, fecha_hasta: date | None
    ) -> None:
        if (
            fecha_desde is not None
            and fecha_hasta is not None
            and fecha_hasta < fecha_desde
        ):
            raise InvalidDateRangeError(
                "fecha_hasta no puede ser anterior a fecha_desde."
            )

    @staticmethod
    def _validate_schedule(hora_inicio: Any, hora_fin: Any) -> None:
        if hora_inicio is None:
            raise InvalidScheduleError("La hora de inicio es obligatoria.")
        if hora_fin is not None and hora_fin <= hora_inicio:
            raise InvalidScheduleError(
                "La hora final debe ser posterior a la hora inicial."
            )

    @staticmethod
    def _normalize_required(value: str, field: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise EventoServiceError(f"El {field} es obligatorio.")
        return normalized

    @staticmethod
    def _normalize_optional(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _evento_values(evento: Evento) -> dict[str, Any]:
        return {
            "id_evento": evento.id_evento,
            "nombre_evento": evento.nombre_evento,
            "descripcion": evento.descripcion,
            "id_area": evento.id_area,
            "flyer_url": evento.flyer_url,
            "estado": evento.estado.value,
        }

    @staticmethod
    def _programacion_values(
        programacion: ProgramacionEvento, lugar: Lugar | None
    ) -> dict[str, Any]:
        return {
            "id_programacion_evento": programacion.id_programacion_evento,
            "modalidad": programacion.modalidad.value,
            "enlace_general": programacion.enlace_general,
            "lugar": EventoService._lugar_values(lugar),
        }

    @staticmethod
    def _dia_values(dia: DetalleProgramacionEvento) -> dict[str, Any]:
        return {
            "id_detalle_programacion": dia.id_detalle_programacion,
            "fecha": dia.fecha.isoformat(),
            "hora_inicio": dia.hora_inicio.isoformat(),
            "hora_fin": dia.hora_fin.isoformat() if dia.hora_fin else None,
            "enlace": dia.enlace,
        }

    @staticmethod
    def _lugar_values(lugar: Lugar | None) -> dict[str, Any] | None:
        if lugar is None:
            return None
        return {
            "id_lugar": lugar.id_lugar,
            "pais": lugar.pais,
            "provincia": lugar.provincia,
            "distrito": lugar.distrito,
            "direccion": lugar.direccion,
            "estado": lugar.estado,
        }

    @staticmethod
    def _lugar_text(lugar: Lugar | None) -> str:
        if lugar is None:
            return ""
        return ", ".join(
            value
            for value in (
                lugar.direccion,
                lugar.distrito,
                lugar.provincia,
                lugar.pais,
            )
            if value
        )

    @classmethod
    def _to_response(cls, detalle: EventoDetalle) -> EventoResponse:
        evento = detalle.evento
        return EventoResponse(
            id_evento=evento.id_evento,
            nombre_evento=evento.nombre_evento,
            descripcion=evento.descripcion,
            id_area=detalle.area.id_area,
            nombre_area=detalle.area.nombre_area,
            flyer_url=evento.flyer_url,
            estado=evento.estado,
            politica=PoliticaEventoResponse(
                id_politica_evento=detalle.politica.id_politica_evento,
                fecha_inicio=detalle.politica.fecha_inicio,
                fecha_fin=detalle.politica.fecha_fin,
                detalles=[
                    DetallePoliticaEventoResponse(
                        id_detalle_politica_evento=item.id_detalle_politica_evento,
                        id_beneficio=beneficio.id_beneficio,
                        nombre_beneficio=beneficio.nombre,
                        id_categoria=categoria.id_categoria,
                        nombre_categoria=categoria.nombre_categoria,
                        entradas_gratuitas=item.entradas_gratuitas,
                    )
                    for item, beneficio, categoria in detalle.detalles
                ],
            ),
        )

    @classmethod
    def _programacion_response(
        cls,
        programacion: ProgramacionEvento,
        lugar: Lugar | None,
        primera_fecha: date | None,
    ) -> ProgramacionEventoResponse:
        return ProgramacionEventoResponse(
            id_programacion_evento=programacion.id_programacion_evento,
            id_evento=programacion.id_evento,
            modalidad=programacion.modalidad,
            enlace_general=programacion.enlace_general,
            estado=programacion.estado,
            lugar=LugarResponse.model_validate(lugar) if lugar else None,
            primera_fecha=primera_fecha,
        )

    @staticmethod
    def _flyer_root() -> Path:
        root = Path(settings.event_flyer_upload_dir).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def _write_atomic(path: Path, content: bytes) -> None:
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        temp_path.write_bytes(content)
        os.replace(temp_path, path)

    @staticmethod
    def _unlink_if_exists(path: Path) -> None:
        path.unlink(missing_ok=True)

    @classmethod
    def _path_from_flyer_url(cls, flyer_url: str) -> Path:
        filename = Path(urlparse(flyer_url).path).name
        return cls._flyer_root() / filename
