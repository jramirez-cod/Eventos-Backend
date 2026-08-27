from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy.exc import NoInspectionAvailable


class LoginRequestDTO(BaseModel):
    nombre_usuario: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1)


class LoginResponseDTO(BaseModel):
    debe_cambiar_password: bool
    token_type: str
    access_token: str | None = None
    password_change_token: str | None = None
    codigo_verificacion_requerido: bool = False
    correo_enmascarado: str | None = None


class OAuthTokenResponseDTO(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CambioPasswordInicialRequestDTO(BaseModel):
    codigo_verificacion: str = Field(
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
    )
    nueva_password: str = Field(min_length=1)
    confirmar_password: str = Field(min_length=1)


class RecuperarPasswordRequestDTO(BaseModel):
    correo: EmailStr


class RecuperarPasswordResponseDTO(BaseModel):
    message: str


class RestablecerPasswordRequestDTO(BaseModel):
    correo: EmailStr
    codigo_verificacion: str = Field(
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
    )
    nueva_password: str = Field(min_length=1)
    confirmar_password: str = Field(min_length=1)


class RolResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_rol: int
    nombre_rol: str
    descripcion: str | None = None
    estado: bool


class TipoDocumentoResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_tipo_documento: int
    nombre_documento: str
    longitud: int | None = None
    estado: bool


class UsuarioCreateDTO(BaseModel):
    id_rol: int
    id_tipo_documento: int
    numero_documento: str = Field(min_length=1, max_length=50)
    nombre_usuario: str = Field(min_length=1, max_length=80)
    nombres: str = Field(min_length=1, max_length=150)
    apellidos: str = Field(min_length=1, max_length=150)
    correo: EmailStr


class UsuarioResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_usuario: int
    nombre_usuario: str
    nombres: str
    apellidos: str
    correo: EmailStr
    id_rol: int
    nombre_rol: str = ""
    id_tipo_documento: int
    nombre_documento: str = ""
    numero_documento: str
    estado: bool
    debe_cambiar_password: bool

    @model_validator(mode="before")
    @classmethod
    def extract_relaciones(cls, data: Any) -> Any:
        rol_is_loaded = False
        tipo_documento_is_loaded = False
        try:
            unloaded = sqlalchemy_inspect(data).unloaded
            rol_is_loaded = "rol" not in unloaded
            tipo_documento_is_loaded = "tipo_documento" not in unloaded
        except NoInspectionAvailable:
            rol_is_loaded = hasattr(data, "rol")
            tipo_documento_is_loaded = hasattr(data, "tipo_documento")

        rol_cargado = rol_is_loaded and getattr(data, "rol", None) is not None
        tipo_documento_cargado = (
            tipo_documento_is_loaded and getattr(data, "tipo_documento", None) is not None
        )

        if rol_cargado or tipo_documento_cargado:
            return {
                "id_usuario": data.id_usuario,
                "nombre_usuario": data.nombre_usuario,
                "nombres": data.nombres,
                "apellidos": data.apellidos,
                "correo": data.correo,
                "id_rol": data.id_rol,
                "nombre_rol": data.rol.nombre_rol if rol_cargado else "",
                "id_tipo_documento": data.id_tipo_documento,
                "nombre_documento": (
                    data.tipo_documento.nombre_documento if tipo_documento_cargado else ""
                ),
                "numero_documento": data.numero_documento,
                "estado": data.estado,
                "debe_cambiar_password": data.debe_cambiar_password,
            }
        return data


class UsuarioUpdateDTO(BaseModel):
    id_rol: int
    id_tipo_documento: int
    numero_documento: str = Field(min_length=1, max_length=50)
    nombres: str = Field(min_length=1, max_length=150)
    apellidos: str = Field(min_length=1, max_length=150)
    correo: EmailStr


class InactivarUsuarioDTO(BaseModel):
    motivo: str | None = Field(default=None, max_length=500)


class MessageResponseDTO(BaseModel):
    message: str
