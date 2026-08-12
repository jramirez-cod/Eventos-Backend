from pydantic import BaseModel, ConfigDict, EmailStr, Field


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
    estado: bool
    debe_cambiar_password: bool


class InactivarUsuarioDTO(BaseModel):
    motivo: str | None = Field(default=None, max_length=500)


class MessageResponseDTO(BaseModel):
    message: str
