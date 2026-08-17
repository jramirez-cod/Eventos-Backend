from pydantic import BaseModel, ConfigDict, Field, field_validator


class GrupoCreateDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre_grupo: str = Field(min_length=1, max_length=120)
    descripcion: str | None = Field(default=None, max_length=255)
    requiere_categoria: bool = False

    @field_validator("nombre_grupo")
    @classmethod
    def validate_nombre_grupo(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("El nombre del grupo es obligatorio.")
        return normalized

    @field_validator("descripcion")
    @classmethod
    def normalize_descripcion(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class GrupoResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_grupo: int
    nombre_grupo: str
    descripcion: str | None
    requiere_categoria: bool
    estado: bool


class GrupoConfiguracionCategoriaDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requiere_categoria: bool
