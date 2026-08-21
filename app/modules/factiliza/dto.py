from pydantic import BaseModel, Field


class RucResponseDTO(BaseModel):
    numero: str
    nombre_o_razon_social: str
    tipo_contribuyente: str | None = None
    estado: str | None = None
    condicion: str | None = None
    departamento: str | None = None
    provincia: str | None = None
    distrito: str | None = None
    direccion: str | None = None
    direccion_completa: str | None = None
    ubigeo_sunat: str | None = None
    ubigeo: list[str] = Field(default_factory=list)


class DniResponseDTO(BaseModel):
    numero: str
    nombres: str
    apellido_paterno: str
    apellido_materno: str
    nombre_completo: str | None = None
    departamento: str | None = None
    provincia: str | None = None
    distrito: str | None = None
    direccion: str | None = None
    direccion_completa: str | None = None
    ubigeo_reniec: str | None = None
    ubigeo_sunat: str | None = None
    ubigeo: list[str] = Field(default_factory=list)
    fecha_nacimiento: str | None = None
    sexo: str | None = None


class CarnetExtranjeriaResponseDTO(BaseModel):
    numero: str
    nombres: str
    apellido_paterno: str
    apellido_materno: str
