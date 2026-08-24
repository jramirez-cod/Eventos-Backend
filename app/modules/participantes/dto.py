from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.contactos.dto import ContactoCreate
from app.modules.participantes.models import ConfirmacionParticipante


class EventoEmpresaCreate(BaseModel):
    id_empresa: int = Field(gt=0)


class EventoEmpresaResponse(BaseModel):
    id_evento_empresa: int
    id_evento: int
    id_empresa: int
    nombre_empresa: str
    ruc: str
    id_grupo: int
    nombre_grupo: str
    id_categoria: int
    nombre_categoria: str
    estado: bool
    creado_en: datetime
    creado_por: int


class ParticipanteCreateMultiple(BaseModel):
    id_evento_empresa: int = Field(gt=0)
    ids_contacto: list[int] = Field(min_length=1, max_length=500)

    @field_validator("ids_contacto")
    @classmethod
    def validar_ids_unicos(cls, values: list[int]) -> list[int]:
        if any(value <= 0 for value in values):
            raise ValueError("Todos los identificadores de contacto deben ser positivos.")
        if len(values) != len(set(values)):
            raise ValueError("La lista contiene contactos repetidos.")
        return values


class ContactoDesdeEventoCreate(BaseModel):
    id_evento_empresa: int = Field(gt=0)
    contacto: ContactoCreate


class ParticipanteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_participante: int
    id_evento_empresa: int
    id_evento: int
    nombre_evento: str
    id_empresa: int
    nombre_empresa: str
    id_contacto: int
    nombre_completo: str
    numero_documento: str | None
    correo: str | None
    celular: str | None
    confirmacion: ConfirmacionParticipante
    estado: bool
    creado_en: datetime
    creado_por: int


class ParticipanteCreateResponse(BaseModel):
    created: int
    participantes: list[ParticipanteResponse]


class ParticipanteListResponse(BaseModel):
    items: list[ParticipanteResponse]
    total: int
    page: int
    page_size: int
    pages: int
