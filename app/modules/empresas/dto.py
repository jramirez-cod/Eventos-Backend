from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.contactos.dto import ContactoCreateData, ContactoResponse


class EmpresaDependienteDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_empresa: int
    nombre_empresa: str
    ruc: str


class EmpresaCreateDTO(BaseModel):
    nombre_empresa: str = Field(min_length=1, max_length=180)
    ruc: str = Field(min_length=11, max_length=11, pattern=r"^\d{11}$")
    id_detalle_categoria: int = Field(gt=0)
    razon_social: str | None = Field(default=None, max_length=250)
    nombre_comercial: str | None = Field(default=None, max_length=180)


class ContactoEmpresaCreateDTO(ContactoCreateData):
    model_config = ConfigDict(extra="forbid")


class EmpresaRegistroCompletoDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    empresa: EmpresaCreateDTO
    contactos: list[ContactoEmpresaCreateDTO] = Field(default_factory=list)


class EmpresaUpdateDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre_empresa: str = Field(min_length=1, max_length=180)
    razon_social: str | None = Field(default=None, max_length=250)
    nombre_comercial: str | None = Field(default=None, max_length=180)


class EmpresaResponseDTO(BaseModel):
    id_empresa: int
    nombre_empresa: str
    ruc: str
    razon_social: str | None
    nombre_comercial: str | None
    estado: bool
    id_grupo: int
    nombre_grupo: str
    id_categoria: int
    nombre_categoria: str


class EmpresaRegistroCompletoResponseDTO(BaseModel):
    empresa: EmpresaResponseDTO
    contactos: list[ContactoResponse]


class ConsultaRucResponseDTO(BaseModel):
    ruc: str
    razon_social: str
    tipo_contribuyente: str | None
    estado: str | None
    condicion: str | None
    direccion: str | None


class CambiarClasificacionDTO(BaseModel):
    id_detalle_categoria: int = Field(gt=0)
    motivo: str | None = Field(default=None, max_length=500)


class InactivarEmpresaDTO(BaseModel):
    motivo: str | None = Field(default=None, max_length=500)


class EmpresaHistorialResponseDTO(BaseModel):
    id_historial: int
    id_detalle_categoria: int
    nombre_grupo: str
    nombre_categoria: str
    fecha_inicio: datetime
    fecha_fin: datetime | None
