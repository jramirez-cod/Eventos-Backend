from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.contactos.dto import ContactoCreate
from app.modules.maestros.models import TipoCalculoBeneficio


class EventoEmpresaCreate(BaseModel):
    id_empresa: int = Field(gt=0)


class EventoEmpresaResponse(BaseModel):
    id_evento_empresa: int
    id_programacion_evento: int
    id_empresa: int
    nombre_empresa: str
    ruc: str
    id_grupo: int
    nombre_grupo: str
    id_categoria: int
    nombre_categoria: str
    id_contacto_principal: int | None
    nombre_contacto_principal: str | None
    codigo_enviado_en: datetime | None
    estado: bool


class ContactoPrincipalUpdate(BaseModel):
    id_contacto: int = Field(gt=0)


class InvitadoCreate(BaseModel):
    nombres: str = Field(min_length=1, max_length=120)
    apellidos: str = Field(min_length=1, max_length=120)
    numero_documento: str | None = Field(default=None, max_length=50)
    correo: str | None = Field(default=None, max_length=254)
    celular: str | None = Field(default=None, max_length=20)


class EstadoEventoContactoUpdate(BaseModel):
    estado: bool


class ReenviarCodigoAccesoRequest(BaseModel):
    motivo: str | None = Field(default=None, max_length=500)


class EventoContactoCreateMultiple(BaseModel):
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
    contacto: ContactoCreate


class EventoContactoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_evento_contacto: int
    id_programacion_evento: int
    id_contacto: int | None
    es_invitado: bool
    nombre_completo: str
    numero_documento: str | None
    correo: str | None
    celular: str | None
    id_empresa: int
    nombre_empresa: str
    estado: bool
    requiere_coordinacion: bool
    asistencia_evento: bool
    hora_ingreso: datetime | None
    credencial_impresa: bool
    id_beneficio_asignado: int | None
    nombre_beneficio_asignado: str | None
    qr_enviado: bool


class EventoContactoCreateResponse(BaseModel):
    created: int
    evento_contactos: list[EventoContactoResponse]


class EventoContactoListResponse(BaseModel):
    items: list[EventoContactoResponse]
    total: int
    page: int
    page_size: int
    pages: int


class AsignarBeneficioRequest(BaseModel):
    ids_evento_contacto: list[int] = Field(min_length=1, max_length=20)
    id_beneficio: int = Field(gt=0)

    @field_validator("ids_evento_contacto")
    @classmethod
    def validar_ids_unicos(cls, values: list[int]) -> list[int]:
        if any(value <= 0 for value in values):
            raise ValueError("Todos los identificadores deben ser positivos.")
        if len(values) != len(set(values)):
            raise ValueError("La lista contiene contactos repetidos.")
        return values


class BeneficioDisponibleResponse(BaseModel):
    id_beneficio: int
    nombre: str
    tipo_calculo: TipoCalculoBeneficio
    personas_por_asignacion: int
    disponible: bool
    cupo_restante: int | None


class EscaneoQrResponse(BaseModel):
    id_evento_contacto: int
    nombre_completo: str
    numero_documento: str | None
    nombre_empresa: str
    id_beneficio_asignado: int | None
    nombre_beneficio_asignado: str | None
    asistencia_evento: bool
    hora_ingreso: datetime | None
    credencial_impresa: bool


class ReimprimirCredencialRequest(BaseModel):
    id_responsable_evento: int = Field(gt=0)
    password: str = Field(min_length=1)


class EnviarQrMasivoResponse(BaseModel):
    enviados: int
    omitidos: int


class EnviarCodigoAccesoMasivoResponse(BaseModel):
    enviados: int
    omitidos: int
    ya_enviados: int
