from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.contactos.dto import ContactoCreate
from app.modules.contactos.service import InvalidPhoneError, normalize_phone
from app.modules.maestros.models import TipoCalculoBeneficio

_NUMERO_DOCUMENTO_INVITADO_RE = re.compile(r"^[A-Za-z0-9]{6,15}$")


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
    numero_documento: str = Field(min_length=1, max_length=50)
    correo: EmailStr
    celular: str | None = Field(default=None, max_length=20)
    id_beneficio: int | None = Field(default=None, gt=0)

    @field_validator("nombres", "apellidos", "numero_documento", mode="before")
    @classmethod
    def limpiar_texto(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("numero_documento")
    @classmethod
    def validar_numero_documento(cls, value: str) -> str:
        if not _NUMERO_DOCUMENTO_INVITADO_RE.fullmatch(value):
            raise ValueError(
                "El número de documento debe tener entre 6 y 15 caracteres "
                "alfanuméricos, sin espacios ni símbolos."
            )
        return value

    @field_validator("celular")
    @classmethod
    def validar_celular(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        try:
            return normalize_phone(value)
        except InvalidPhoneError as exc:
            raise ValueError(str(exc)) from exc


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
