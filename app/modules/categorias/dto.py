from pydantic import BaseModel, ConfigDict, Field, field_validator


class CategoriaCreateDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_grupo: int = Field(gt=0)
    nombre_categoria: str = Field(min_length=1, max_length=120)
    descripcion: str | None = Field(default=None, max_length=255)

    @field_validator("nombre_categoria")
    @classmethod
    def validate_nombre_categoria(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("El nombre de la categoría es obligatorio.")
        return normalized

    @field_validator("descripcion")
    @classmethod
    def normalize_descripcion(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class CategoriaResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_categoria: int
    nombre_categoria: str
    descripcion: str | None
    estado: bool


class CategoriaGrupoResponseDTO(CategoriaResponseDTO):
    id_grupo: int
    id_detalle_categoria: int
    estado_relacion: bool
