from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CorreoPlantillaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_plantilla: int
    codigo: str
    nombre: str
    asunto: str
    cuerpo_html: str
    cuerpo_texto: str
    variables_permitidas: list[str]
    version_actual: int
    estado: bool
    creado_en: datetime
    actualizado_en: datetime


class CorreoPlantillaListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_plantilla: int
    codigo: str
    nombre: str
    asunto: str
    variables_permitidas: list[str]
    version_actual: int
    estado: bool
    actualizado_en: datetime


class CorreoPlantillaUpdate(BaseModel):
    asunto: str = Field(min_length=1, max_length=255)
    cuerpo_html: str = Field(min_length=1, max_length=200_000)
    cuerpo_texto: str = Field(min_length=1, max_length=50_000)
    estado: bool
    version_esperada: int = Field(ge=1)
    motivo: str = Field(min_length=3, max_length=255)


class CorreoPlantillaPreviewRequest(BaseModel):
    asunto: str | None = Field(default=None, min_length=1, max_length=255)
    cuerpo_html: str | None = Field(default=None, min_length=1, max_length=200_000)
    cuerpo_texto: str | None = Field(default=None, min_length=1, max_length=50_000)
    contexto: dict[str, Any] = Field(default_factory=dict)


class CorreoPlantillaPreviewResponse(BaseModel):
    asunto: str
    cuerpo_html: str
    cuerpo_texto: str


class CorreoPlantillaHistorialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_historial: int
    id_plantilla: int
    version: int
    asunto: str
    cuerpo_html: str
    cuerpo_texto: str
    motivo: str | None
    creado_por: int | None
    creado_en: datetime


class CorreoPlantillaRestaurarRequest(BaseModel):
    version_esperada: int = Field(ge=1)
    motivo: str = Field(min_length=3, max_length=255)


class CorreoConfiguracionGlobalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_configuracion: int
    codigo: str
    id_usuario_emisor: int
    correo_emisor: EmailStr
    nombre_remitente: str
    reply_to: EmailStr | None
    estado: bool
    creado_en: datetime
    actualizado_en: datetime


class CorreoConfiguracionGlobalUpdate(BaseModel):
    id_usuario_emisor: int = Field(gt=0)
    nombre_remitente: str = Field(min_length=1, max_length=120)
    reply_to: EmailStr | None = None
    estado: bool


class CorreoPruebaRequest(BaseModel):
    destinatario: EmailStr
    contexto: dict[str, Any]


class CorreoOperacionResponse(BaseModel):
    message: str

