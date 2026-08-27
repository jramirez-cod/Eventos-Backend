from pydantic import BaseModel, Field, field_validator

from app.modules.participantes.dto import BeneficioDisponibleResponse, InvitadoCreate


class ValidarCodigoRequest(BaseModel):
    codigo: str = Field(min_length=1, max_length=32)


class ValidarCodigoResponse(BaseModel):
    portal_token: str
    nombre_empresa: str
    nombre_evento: str
    nombre_contacto_principal: str
    nombre_categoria: str


class PortalContactoDisponible(BaseModel):
    id_contacto: int
    nombre_completo: str
    numero_documento: str | None
    ya_agregado: bool
    beneficios_disponibles: list[BeneficioDisponibleResponse]


class PortalParticipanteSeleccion(BaseModel):
    id_contacto: int = Field(gt=0)
    id_beneficio: int | None = None


class AgregarParticipantesPortalRequest(BaseModel):
    selecciones: list[PortalParticipanteSeleccion] = Field(min_length=1, max_length=200)

    @field_validator("selecciones")
    @classmethod
    def validar_ids_unicos(
        cls, values: list[PortalParticipanteSeleccion]
    ) -> list[PortalParticipanteSeleccion]:
        ids = [seleccion.id_contacto for seleccion in values]
        if len(ids) != len(set(ids)):
            raise ValueError("La lista contiene contactos repetidos.")
        return values


__all__ = [
    "AgregarParticipantesPortalRequest",
    "InvitadoCreate",
    "PortalContactoDisponible",
    "PortalParticipanteSeleccion",
    "ValidarCodigoRequest",
    "ValidarCodigoResponse",
]
