from datetime import date, datetime, time
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


class EventoCreate(BaseModel):
    nombre_evento: str = Field(min_length=1, max_length=200)
    descripcion: str | None = None
    fecha_inicio: date
    fecha_fin: date
    aforo: int | None = Field(default=None, ge=0)
    modalidad: EventoModalidad
    enlace_general: str | None = Field(default=None, max_length=500)
    lugar: LugarCreate | None = None
    hora_inicio: time
    hora_fin: time | None = None

    @field_validator("nombre_evento", mode="before")
    @classmethod
    def limpiar_nombre(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("descripcion", "enlace_general", mode="before")
    @classmethod
    def limpiar_opcional(cls, value: object) -> object:
        return _strip_optional(value)


class EventoUpdate(BaseModel):
    nombre_evento: str | None = Field(default=None, min_length=1, max_length=200)
    descripcion: str | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    aforo: int | None = Field(default=None, ge=0)

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
    estado: bool
    lugar: LugarResponse | None


class DetalleProgramacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_detalle_programacion: int
    id_programacion_evento: int
    fecha: date
    hora_inicio: time
    hora_fin: time | None
    enlace: str | None
    estado: bool


class EventoResponse(BaseModel):
    id_evento: int
    nombre_evento: str
    descripcion: str | None
    fecha_inicio: date
    fecha_fin: date
    aforo: int | None
    flyer_url: str | None
    estado: EventoEstado
    creado_por: int
    creado_en: datetime
    actualizado_en: datetime
    programacion: ProgramacionEventoResponse


class EventoListItem(EventoResponse):
    pass


class EventoListResponse(BaseModel):
    items: list[EventoListItem]
    total: int
    page: int
    page_size: int
    pages: int
