from datetime import date, time
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.eventos.models import EventoEstado, EventoModalidad


def _strip_optional(value: object) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


class LugarCreate(BaseModel):
    pais: str | None = Field(default=None, max_length=100)
    provincia: str | None = Field(default=None, max_length=100)
    distrito: str | None = Field(default=None, max_length=100)
    direccion: str | None = Field(default=None, max_length=255)

    @field_validator("pais", "provincia", "distrito", "direccion", mode="before")
    @classmethod
    def limpiar_texto(cls, value: object) -> object:
        return _strip_optional(value)

    @model_validator(mode="after")
    def validar_contenido(self) -> Self:
        if not any((self.pais, self.provincia, self.distrito, self.direccion)):
            raise ValueError("El lugar debe contener al menos un dato de ubicación.")
        return self


class LugarResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_lugar: int
    pais: str | None
    provincia: str | None
    distrito: str | None
    direccion: str | None
    estado: bool


class DetallePoliticaEventoCreate(BaseModel):
    id_beneficio: int = Field(gt=0)
    id_categoria: int = Field(gt=0)
    entradas_gratuitas: int = Field(default=0, ge=0)


class DetallePoliticaEventoResponse(BaseModel):
    id_detalle_politica_evento: int
    id_beneficio: int
    nombre_beneficio: str
    id_categoria: int
    nombre_categoria: str
    entradas_gratuitas: int


class PoliticaEventoCreate(BaseModel):
    fecha_inicio: date
    fecha_fin: date
    detalles: list[DetallePoliticaEventoCreate] = Field(min_length=1)

    @field_validator("detalles")
    @classmethod
    def validar_categorias_unicas(
        cls, value: list[DetallePoliticaEventoCreate]
    ) -> list[DetallePoliticaEventoCreate]:
        categorias = [detalle.id_categoria for detalle in value]
        if len(categorias) != len(set(categorias)):
            raise ValueError(
                "Cada categoría solo puede tener un beneficio asignado en la política."
            )
        return value


class PoliticaEventoResponse(BaseModel):
    id_politica_evento: int
    fecha_inicio: date
    fecha_fin: date
    detalles: list[DetallePoliticaEventoResponse]


class EventoCreate(BaseModel):
    nombre_evento: str = Field(min_length=1, max_length=200)
    descripcion: str | None = None
    id_area: int = Field(gt=0)
    politica: PoliticaEventoCreate

    @field_validator("nombre_evento", mode="before")
    @classmethod
    def limpiar_nombre(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("descripcion", mode="before")
    @classmethod
    def limpiar_descripcion(cls, value: object) -> object:
        return _strip_optional(value)


class EventoUpdate(BaseModel):
    nombre_evento: str | None = Field(default=None, min_length=1, max_length=200)
    descripcion: str | None = None
    id_area: int | None = Field(default=None, gt=0)

    @field_validator("nombre_evento", mode="before")
    @classmethod
    def limpiar_nombre(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("descripcion", mode="before")
    @classmethod
    def limpiar_descripcion(cls, value: object) -> object:
        return _strip_optional(value)

    @model_validator(mode="after")
    def validar_contenido(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Debe enviar al menos un campo para actualizar.")
        return self


class PoliticaEventoUpdate(BaseModel):
    fecha_inicio: date
    fecha_fin: date
    detalles: list[DetallePoliticaEventoCreate] = Field(min_length=1)

    @field_validator("detalles")
    @classmethod
    def validar_categorias_unicas(
        cls, value: list[DetallePoliticaEventoCreate]
    ) -> list[DetallePoliticaEventoCreate]:
        categorias = [detalle.id_categoria for detalle in value]
        if len(categorias) != len(set(categorias)):
            raise ValueError(
                "Cada categoría solo puede tener un beneficio asignado en la política."
            )
        return value


class ProgramacionDiaCreate(BaseModel):
    fecha: date
    hora_inicio: time
    hora_fin: time | None = None
    enlace: str | None = Field(default=None, max_length=500)

    @field_validator("enlace", mode="before")
    @classmethod
    def limpiar_enlace(cls, value: object) -> object:
        return _strip_optional(value)

    @field_validator("fecha")
    @classmethod
    def validar_fecha_no_pasada(cls, value: date) -> date:
        if value < date.today():
            raise ValueError("La fecha no puede ser anterior al día de hoy.")
        return value

    @model_validator(mode="after")
    def validar_horas(self) -> Self:
        if self.hora_fin is not None and self.hora_fin <= self.hora_inicio:
            raise ValueError("La hora final debe ser posterior a la hora inicial.")
        return self


class ProgramacionEventoCreate(BaseModel):
    modalidad: EventoModalidad
    enlace_general: str | None = Field(default=None, max_length=500)
    lugar: LugarCreate | None = None
    dias: list[ProgramacionDiaCreate] = Field(min_length=1)

    @field_validator("enlace_general", mode="before")
    @classmethod
    def limpiar_enlace(cls, value: object) -> object:
        return _strip_optional(value)

    @field_validator("dias")
    @classmethod
    def validar_fechas_unicas(
        cls, value: list[ProgramacionDiaCreate]
    ) -> list[ProgramacionDiaCreate]:
        fechas = [dia.fecha for dia in value]
        if len(fechas) != len(set(fechas)):
            raise ValueError("No se puede repetir la misma fecha en una programación.")
        return value

    @model_validator(mode="after")
    def validar_lugar_requerido(self) -> Self:
        if (
            self.modalidad in (EventoModalidad.PRESENCIAL, EventoModalidad.HIBRIDO)
            and self.lugar is None
        ):
            raise ValueError(
                "Debe especificar un lugar para programaciones presenciales o híbridas."
            )
        if self.modalidad == EventoModalidad.VIRTUAL and self.lugar is not None:
            raise ValueError(
                "Las programaciones virtuales no admiten un lugar físico."
            )
        return self


class ProgramacionEventoUpdate(BaseModel):
    modalidad: EventoModalidad | None = None
    enlace_general: str | None = Field(default=None, max_length=500)
    lugar: LugarCreate | None = None

    @field_validator("enlace_general", mode="before")
    @classmethod
    def limpiar_enlace(cls, value: object) -> object:
        return _strip_optional(value)

    @model_validator(mode="after")
    def validar_contenido(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Debe enviar al menos un campo para actualizar.")
        return self


class DetalleProgramacionUpdate(BaseModel):
    hora_inicio: time | None = None
    hora_fin: time | None = None
    enlace: str | None = Field(default=None, max_length=500)

    @field_validator("enlace", mode="before")
    @classmethod
    def limpiar_enlace(cls, value: object) -> object:
        return _strip_optional(value)

    @model_validator(mode="after")
    def validar_contenido(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Debe enviar al menos un campo para actualizar.")
        return self


class EventoFinalizarRequest(BaseModel):
    motivo: str | None = Field(default=None, max_length=500)

    @field_validator("motivo", mode="before")
    @classmethod
    def limpiar_motivo(cls, value: object) -> object:
        return _strip_optional(value)


class EventoReabrirRequest(BaseModel):
    motivo: str = Field(min_length=1, max_length=500)

    @field_validator("motivo")
    @classmethod
    def motivo_obligatorio(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El motivo es obligatorio.")
        return value


class EventoInactivarRequest(BaseModel):
    motivo: str | None = Field(default=None, max_length=500)

    @field_validator("motivo", mode="before")
    @classmethod
    def limpiar_motivo(cls, value: object) -> object:
        return _strip_optional(value)


class ProgramacionEventoResponse(BaseModel):
    id_programacion_evento: int
    id_evento: int
    modalidad: EventoModalidad
    enlace_general: str | None
    estado: EventoEstado
    lugar: LugarResponse | None
    primera_fecha: date | None


class ProgramacionEventoListResponse(BaseModel):
    items: list[ProgramacionEventoResponse]
    total: int
    page: int
    page_size: int
    pages: int


class ProgramacionEventoTransversalResponse(ProgramacionEventoResponse):
    nombre_evento: str


class ProgramacionEventoTransversalListResponse(BaseModel):
    items: list[ProgramacionEventoTransversalResponse]
    total: int
    page: int
    page_size: int
    pages: int


class DetalleProgramacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_detalle_programacion: int
    id_programacion_evento: int
    fecha: date
    hora_inicio: time
    hora_fin: time | None
    enlace: str | None
    estado: bool


class ResponsableEventoCreate(BaseModel):
    id_usuario: int = Field(gt=0)


class ResponsableEventoResponse(BaseModel):
    id_responsable_evento: int
    id_programacion_evento: int
    id_usuario: int
    nombre_usuario: str
    estado: bool


class EventoResponse(BaseModel):
    id_evento: int
    nombre_evento: str
    descripcion: str | None
    id_area: int
    nombre_area: str
    flyer_url: str | None
    estado: EventoEstado
    politica: PoliticaEventoResponse


class EventoListItem(EventoResponse):
    pass


class EventoListResponse(BaseModel):
    items: list[EventoListItem]
    total: int
    page: int
    page_size: int
    pages: int
