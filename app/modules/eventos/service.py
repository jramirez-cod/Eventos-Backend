from datetime import date, datetime, timedelta
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
    EventoCreate,
    EventoListItem,
    EventoListResponse,
    EventoResponse,
    EventoUpdate,
    LugarCreate,
    LugarResponse,
    ProgramacionEventoResponse,
    ProgramacionEventoUpdate,
)
from app.modules.eventos.models import (
    DetalleProgramacionEvento,
    Evento,
    EventoEstado,
    EventoModalidad,
    Lugar,
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


class ProgramacionNotFoundError(EventoServiceError):
    pass


class DiaNotFoundError(EventoServiceError):
    pass


class InvalidDateRangeError(EventoServiceError):
    pass


class InvalidScheduleError(EventoServiceError):
    pass


class InvalidStateTransitionError(EventoServiceError):
    pass


class EventoNotEditableError(EventoServiceError):
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


def generar_dias_evento(fecha_inicio: date, fecha_fin: date) -> list[date]:
    return [
        fecha_inicio + timedelta(days=offset)
        for offset in range((fecha_fin - fecha_inicio).days + 1)
    ]


class EventoService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.eventos = EventoRepository(db)
        self.usuarios = UsuarioRepository(db)
        self.auditoria = AuditoriaRepository(db)

    async def crear_evento(
        self, *, data: EventoCreate, actor: Usuario
    ) -> EventoResponse:
        self._validate_date_range(data.fecha_inicio, data.fecha_fin)
        self._validate_schedule(data.hora_inicio, data.hora_fin)
        nombre = self._normalize_required(data.nombre_evento, "nombre del evento")
        nombre_repetido = await self.eventos.count_by_name(nombre) > 0

        try:
            lugar = await self._create_lugar(data.lugar)
            evento = await self.eventos.create_evento(
                nombre_evento=nombre,
                descripcion=self._normalize_optional(data.descripcion),
                fecha_inicio=data.fecha_inicio,
                fecha_fin=data.fecha_fin,
                aforo=data.aforo,
                creado_por=actor.id_usuario,
            )
            programacion = await self.eventos.create_programacion(
                id_evento=evento.id_evento,
                id_lugar=lugar.id_lugar if lugar else None,
                modalidad=data.modalidad,
                enlace_general=self._normalize_optional(data.enlace_general),
            )
            for fecha in generar_dias_evento(data.fecha_inicio, data.fecha_fin):
                await self.eventos.create_dia(
                    id_programacion_evento=programacion.id_programacion_evento,
                    fecha=fecha,
                    hora_inicio=data.hora_inicio,
                    hora_fin=data.hora_fin,
                    enlace=self._normalize_optional(data.enlace_general),
                )
            audit_values = self._evento_values(evento)
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
        modalidad: EventoModalidad | None,
        page: int,
        page_size: int,
    ) -> EventoListResponse:
        self._validate_filter_dates(fecha_desde, fecha_hasta)
        rows, total = await self.eventos.list_detallado(
            search=search,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            estado=estado,
            modalidad=modalidad,
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

        nueva_fecha_inicio = values.get("fecha_inicio", evento.fecha_inicio)
        nueva_fecha_fin = values.get("fecha_fin", evento.fecha_fin)
        if "fecha_inicio" in values or "fecha_fin" in values:
            self._validate_date_range(nueva_fecha_inicio, nueva_fecha_fin)

        anterior = self._evento_values(evento)
        try:
            await self.eventos.update_evento(evento, values)
            if "fecha_inicio" in values or "fecha_fin" in values:
                await self._sync_dias(evento)
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

    async def obtener_programacion(
        self, id_evento: int
    ) -> ProgramacionEventoResponse:
        detalle = await self.eventos.get_detallado(id_evento)
        if detalle is None:
            raise EventoNotFoundError("Evento no encontrado.")
        return self._programacion_response(detalle.programacion, detalle.lugar)

    async def actualizar_programacion(
        self,
        *,
        id_evento: int,
        data: ProgramacionEventoUpdate,
        actor: Usuario,
    ) -> ProgramacionEventoResponse:
        evento = await self._get_evento_for_update(id_evento)
        self.validar_evento_abierto(evento)
        programacion = await self.eventos.get_programacion(
            id_evento, for_update=True
        )
        if programacion is None:
            raise ProgramacionNotFoundError("Programación del evento no encontrada.")
        lugar_actual = (
            await self.db.get(Lugar, programacion.id_lugar)
            if programacion.id_lugar is not None
            else None
        )
        anterior = self._programacion_values(programacion, lugar_actual)
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
        return await self.obtener_programacion(id_evento)

    async def listar_dias(
        self, id_evento: int
    ) -> list[DetalleProgramacionResponse]:
        if await self.eventos.get_by_id(id_evento) is None:
            raise EventoNotFoundError("Evento no encontrado.")
        dias = await self.eventos.list_dias(id_evento)
        return [DetalleProgramacionResponse.model_validate(dia) for dia in dias]

    async def actualizar_dia(
        self,
        *,
        id_evento: int,
        id_dia: int,
        data: DetalleProgramacionUpdate,
        actor: Usuario,
    ) -> DetalleProgramacionResponse:
        evento = await self._get_evento_for_update(id_evento)
        self.validar_evento_abierto(evento)
        dia = await self.eventos.get_dia(
            id_evento=id_evento, id_dia=id_dia, for_update=True
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
                    "REEMPLAZAR_FLYER_EVENTO"
                    if old_url
                    else "ADJUNTAR_FLYER_EVENTO"
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

    async def eliminar_evento(self, *, id_evento: int, actor: Usuario) -> None:
        evento = await self._get_evento_for_update(id_evento)
        if await self.eventos.has_participant_dependencies(id_evento):
            raise EventoDependencyError(
                "No se puede eliminar el evento porque tiene participantes asociados."
            )
        programacion = await self.eventos.get_programacion(
            id_evento, for_update=True
        )
        old_lugar_id = programacion.id_lugar if programacion else None
        old_flyer_url = evento.flyer_url

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
            await self.eventos.delete_lugar_if_orphan(old_lugar_id)
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
        modalidad: EventoModalidad | None,
    ) -> bytes:
        self._validate_filter_dates(fecha_desde, fecha_hasta)
        rows, _ = await self.eventos.list_detallado(
            search=search,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            estado=estado,
            modalidad=modalidad,
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
                "Fecha inicio",
                "Fecha fin",
                "Modalidad",
                "Lugar",
                "Aforo",
                "Estado",
            ]
        )
        for row in rows:
            sheet.append(
                [
                    row.evento.id_evento,
                    row.evento.nombre_evento,
                    row.evento.descripcion or "",
                    row.evento.fecha_inicio,
                    row.evento.fecha_fin,
                    row.programacion.modalidad.value,
                    self._lugar_text(row.lugar),
                    row.evento.aforo,
                    row.evento.estado.value,
                ]
            )
        output = BytesIO()
        workbook.save(output)
        workbook.close()
        return output.getvalue()

    async def _sync_dias(self, evento: Evento) -> None:
        programacion = await self.eventos.get_programacion(
            evento.id_evento, for_update=True
        )
        if programacion is None:
            raise ProgramacionNotFoundError("Programación del evento no encontrada.")
        actuales = await self.eventos.list_dias(evento.id_evento, for_update=True)
        if not actuales:
            raise ProgramacionNotFoundError("El evento no tiene días configurados.")
        actuales_por_fecha = {dia.fecha: dia for dia in actuales}
        objetivo = generar_dias_evento(evento.fecha_inicio, evento.fecha_fin)
        objetivo_set = set(objetivo)
        plantilla = actuales[0]

        for dia in actuales:
            if dia.fecha not in objetivo_set:
                await self.eventos.delete_dia(dia)
        for fecha in objetivo:
            if fecha not in actuales_por_fecha:
                await self.eventos.create_dia(
                    id_programacion_evento=programacion.id_programacion_evento,
                    fecha=fecha,
                    hora_inicio=plantilla.hora_inicio,
                    hora_fin=plantilla.hora_fin,
                    enlace=plantilla.enlace,
                )
        await self.db.flush()

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

    async def _get_evento_for_update(self, id_evento: int) -> Evento:
        evento = await self.eventos.get_by_id_for_update(id_evento)
        if evento is None:
            raise EventoNotFoundError("Evento no encontrado.")
        return evento

    async def _create_lugar(self, data: LugarCreate | None) -> Lugar | None:
        if data is None:
            return None
        return await self.eventos.create_lugar(**data.model_dump())

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
            "fecha_inicio": evento.fecha_inicio.isoformat(),
            "fecha_fin": evento.fecha_fin.isoformat(),
            "aforo": evento.aforo,
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
            fecha_inicio=evento.fecha_inicio,
            fecha_fin=evento.fecha_fin,
            aforo=evento.aforo,
            flyer_url=evento.flyer_url,
            estado=evento.estado,
            creado_por=evento.creado_por,
            creado_en=evento.creado_en,
            actualizado_en=evento.actualizado_en,
            programacion=cls._programacion_response(
                detalle.programacion, detalle.lugar
            ),
        )

    @classmethod
    def _programacion_response(
        cls, programacion: ProgramacionEvento, lugar: Lugar | None
    ) -> ProgramacionEventoResponse:
        return ProgramacionEventoResponse(
            id_programacion_evento=programacion.id_programacion_evento,
            id_evento=programacion.id_evento,
            modalidad=programacion.modalidad,
            enlace_general=programacion.enlace_general,
            estado=programacion.estado,
            lugar=LugarResponse.model_validate(lugar) if lugar else None,
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
