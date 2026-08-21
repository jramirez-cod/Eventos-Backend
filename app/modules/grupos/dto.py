from pydantic import BaseModel, ConfigDict, Field


class GrupoCreateDTO(BaseModel):
    id_grupo: int = Field(gt=0)
    nombre_grupo: str = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=255)


class GrupoUpdateDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre_grupo: str = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=255)


class GrupoResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_grupo: int
    nombre_grupo: str
    descripcion: str | None
    estado: bool


class InactivarGrupoDTO(BaseModel):
    motivo: str | None = Field(default=None, max_length=500)


class AsignarCategoriaDTO(BaseModel):
    id_categoria: int = Field(gt=0)


class CategoriaAsignadaResponseDTO(BaseModel):
    id_detalle_categoria: int
    id_grupo: int
    id_categoria: int
    nombre_categoria: str
    estado: bool
