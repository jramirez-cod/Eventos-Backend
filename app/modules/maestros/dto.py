from pydantic import BaseModel, ConfigDict, Field

from app.modules.maestros.models import TipoCalculoBeneficio


class CargoCreate(BaseModel):
    nombre_cargo: str = Field(min_length=1, max_length=100)


class CargoUpdate(BaseModel):
    nombre_cargo: str = Field(min_length=1, max_length=100)


class CargoEstadoUpdate(BaseModel):
    estado: bool


class CargoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_cargo: int
    nombre_cargo: str
    estado: bool


class CargoListResponse(BaseModel):
    items: list[CargoResponse]
    total: int
    page: int
    page_size: int
    pages: int


class AreaCreate(BaseModel):
    nombre_area: str = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=255)


class AreaUpdate(BaseModel):
    nombre_area: str = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=255)


class AreaEstadoUpdate(BaseModel):
    estado: bool


class AreaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_area: int
    nombre_area: str
    descripcion: str | None
    estado: bool


class AreaListResponse(BaseModel):
    items: list[AreaResponse]
    total: int
    page: int
    page_size: int
    pages: int


class BeneficioCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    condicion: str | None = Field(default=None, max_length=255)
    tipo_calculo: TipoCalculoBeneficio = TipoCalculoBeneficio.POR_EVENTO
    personas_por_asignacion: int = Field(default=1, ge=1)


class BeneficioUpdate(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    condicion: str | None = Field(default=None, max_length=255)
    tipo_calculo: TipoCalculoBeneficio = TipoCalculoBeneficio.POR_EVENTO
    personas_por_asignacion: int = Field(default=1, ge=1)


class BeneficioEstadoUpdate(BaseModel):
    estado: bool


class BeneficioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_beneficio: int
    nombre: str
    condicion: str | None
    tipo_calculo: TipoCalculoBeneficio
    personas_por_asignacion: int
    estado: bool


class BeneficioListResponse(BaseModel):
    items: list[BeneficioResponse]
    total: int
    page: int
    page_size: int
    pages: int
