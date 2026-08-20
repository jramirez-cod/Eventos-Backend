from pydantic import BaseModel, ConfigDict, Field


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
