from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)


Genero = Literal["M", "F", "OTRO"]


class ContactoCreateData(BaseModel):
    id_cargo: int | None = Field(default=None, gt=0)
    id_tipo_documento: int | None = Field(default=None, gt=0)
    numero_documento: str | None = Field(default=None, min_length=1, max_length=30)
    nombres: str = Field(min_length=1, max_length=120)
    apellidos: str = Field(min_length=1, max_length=120)
    genero: Genero
    celular: str | None = Field(default=None, min_length=1, max_length=50)
    correo: EmailStr | None = None
    es_contacto_principal: bool = False

    @field_validator("nombres", "apellidos", "numero_documento", mode="before")
    @classmethod
    def limpiar_texto(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("genero", mode="before")
    @classmethod
    def normalizar_genero(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validar_documento_completo(self) -> Self:
        if (self.id_tipo_documento is None) != (self.numero_documento is None):
            raise ValueError(
                "id_tipo_documento y numero_documento deben enviarse juntos."
            )
        return self


class ContactoCreate(ContactoCreateData):
    id_empresa: int = Field(gt=0)


class ContactoUpdate(BaseModel):
    id_cargo: int | None = Field(default=None, gt=0)
    id_tipo_documento: int | None = Field(default=None, gt=0)
    numero_documento: str | None = Field(default=None, min_length=1, max_length=30)
    nombres: str | None = Field(default=None, min_length=1, max_length=120)
    apellidos: str | None = Field(default=None, min_length=1, max_length=120)
    genero: Genero | None = None
    celular: str | None = Field(default=None, min_length=1, max_length=50)
    correo: EmailStr | None = None
    es_contacto_principal: bool | None = None

    @field_validator("nombres", "apellidos", "numero_documento", mode="before")
    @classmethod
    def limpiar_texto(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("genero", mode="before")
    @classmethod
    def normalizar_genero(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validar_contenido(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Debe enviar al menos un campo para actualizar.")
        return self


class ContactoEstadoUpdate(BaseModel):
    estado: bool
    motivo: str | None = Field(default=None, max_length=500)


class ContactoCambiarEmpresaRequest(BaseModel):
    id_empresa: int = Field(gt=0)
    motivo: str = Field(min_length=1, max_length=500)

    @field_validator("motivo")
    @classmethod
    def motivo_no_vacio(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El motivo es obligatorio.")
        return value


class ContactoFusionRequest(BaseModel):
    id_contacto_principal: int = Field(gt=0)
    id_contacto_duplicado: int = Field(gt=0)
    motivo: str = Field(min_length=1, max_length=500)

    @field_validator("motivo")
    @classmethod
    def motivo_no_vacio(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El motivo es obligatorio.")
        return value


class ContactoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_contacto: int
    id_empresa: int
    nombre_empresa: str
    id_cargo: int | None
    nombre_cargo: str | None
    id_tipo_documento: int | None
    nombre_tipo_documento: str | None
    numero_documento: str | None
    nombres: str
    apellidos: str
    nombre_completo: str
    genero: Genero
    celular: str | None
    correo: str | None
    es_contacto_principal: bool
    estado: bool


class ContactoListItem(ContactoResponse):
    pass


class ContactoPage(BaseModel):
    items: list[ContactoListItem]
    total: int
    page: int
    page_size: int
    pages: int
