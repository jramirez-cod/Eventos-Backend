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


class OAuthTokenResponseDTO(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CambioPasswordInicialRequestDTO(BaseModel):
    nueva_password: str = Field(min_length=1)
    confirmar_password: str = Field(min_length=1)


class RecuperarPasswordRequestDTO(BaseModel):
    correo: EmailStr


class RecuperarPasswordResponseDTO(BaseModel):
    message: str


class RestablecerPasswordRequestDTO(BaseModel):
    token: str = Field(min_length=1)
    nueva_password: str = Field(min_length=1)
    confirmar_password: str = Field(min_length=1)


class RolResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_rol: int
    nombre_rol: str
    descripcion: str | None = None
    estado: bool


class UsuarioCreateDTO(BaseModel):
    id_rol: int
    nombre_usuario: str = Field(min_length=1, max_length=80)
    nombres: str = Field(min_length=1, max_length=150)
    apellidos: str = Field(min_length=1, max_length=150)
    correo: EmailStr
    password_temporal: str = Field(min_length=1)


class UsuarioResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_usuario: int
    nombre_usuario: str
    nombres: str
    apellidos: str
    correo: EmailStr
    id_rol: int
    nombre_rol: str = ""
    estado: bool
    debe_cambiar_password: bool

    @model_validator(mode="before")
    @classmethod
    def extract_nombre_rol(cls, data: Any) -> Any:
        rol_is_loaded = False
        try:
            rol_is_loaded = "rol" not in sqlalchemy_inspect(data).unloaded
        except NoInspectionAvailable:
            rol_is_loaded = hasattr(data, "rol")

        if rol_is_loaded and getattr(data, "rol", None) is not None:
            return {
                "id_usuario": data.id_usuario,
                "nombre_usuario": data.nombre_usuario,
                "nombres": data.nombres,
                "apellidos": data.apellidos,
                "correo": data.correo,
                "id_rol": data.id_rol,
                "nombre_rol": data.rol.nombre_rol,
                "estado": data.estado,
                "debe_cambiar_password": data.debe_cambiar_password,
            }
        return data


class InactivarUsuarioDTO(BaseModel):
    motivo: str | None = Field(default=None, max_length=500)


class MessageResponseDTO(BaseModel):
    message: str
