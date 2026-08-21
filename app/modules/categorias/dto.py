from pydantic import BaseModel, ConfigDict, Field


class CategoriaCreateDTO(BaseModel):
    nombre_categoria: str = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=255)


class CategoriaUpdateDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre_categoria: str = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=255)


class CategoriaResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_categoria: int
    nombre_categoria: str
    descripcion: str | None
    estado: bool


class InactivarCategoriaDTO(BaseModel):
    motivo: str | None = Field(default=None, max_length=500)
