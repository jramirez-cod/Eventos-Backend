from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Rol(Base):
    __tablename__ = "rol"

    id_rol: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    nombre_rol: Mapped[str] = mapped_column(
        "nombre", String(80), nullable=False, unique=True
    )
    descripcion: Mapped[str | None] = mapped_column(String(255))
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    usuarios: Mapped[list["Usuario"]] = relationship(back_populates="rol")


class TipoDocumento(Base):
    __tablename__ = "tipo_documento"

    id_tipo_documento: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True
    )
    nombre_documento: Mapped[str] = mapped_column(String(50), nullable=False)
    longitud: Mapped[int | None] = mapped_column(Integer)
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    usuarios: Mapped[list["Usuario"]] = relationship(back_populates="tipo_documento")


class Usuario(Base):
    __tablename__ = "usuario"

    id_usuario: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    id_rol: Mapped[int] = mapped_column(ForeignKey("rol.id_rol"), nullable=False)
    id_tipo_documento: Mapped[int] = mapped_column(
        ForeignKey("tipo_documento.id_tipo_documento"), nullable=False
    )
    numero_documento: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True
    )
    nombre_usuario: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    nombres: Mapped[str] = mapped_column(String(120), nullable=False)
    apellidos: Mapped[str] = mapped_column(String(120), nullable=False)
    correo: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    debe_cambiar_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    rol: Mapped[Rol] = relationship(back_populates="usuarios")
    tipo_documento: Mapped[TipoDocumento] = relationship(back_populates="usuarios")
    tokens_recuperacion: Mapped[list["UsuarioTokenRecuperacion"]] = relationship(
        back_populates="usuario"
    )


class UsuarioTokenRecuperacion(Base):
    __tablename__ = "usuario_token_recuperacion"

    id_usuario_token: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True
    )
    id_usuario: Mapped[int] = mapped_column(
        ForeignKey("usuario.id_usuario"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    utilizado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    usuario: Mapped[Usuario] = relationship(back_populates="tokens_recuperacion")


class Modulo(Base):
    __tablename__ = "modulo"

    id_modulo: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    nombre_modulo: Mapped[str] = mapped_column(
        "nombre", String(100), nullable=False, unique=True
    )
    descripcion: Mapped[str | None] = mapped_column(String(255))
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Permiso(Base):
    __tablename__ = "permiso"

    id_permiso: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    codigo: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    nombre_permiso: Mapped[str] = mapped_column(
        "nombre", String(120), nullable=False
    )
    descripcion: Mapped[str | None] = mapped_column(String(255))
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class RolPermisoModulo(Base):
    __tablename__ = "rol_permiso_modulo"

    id_rol_permiso: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True
    )
    id_rol: Mapped[int] = mapped_column(ForeignKey("rol.id_rol"), nullable=False)
    id_permiso: Mapped[int] = mapped_column(
        ForeignKey("permiso.id_permiso"), nullable=False
    )
    id_modulo: Mapped[int] = mapped_column(
        ForeignKey("modulo.id_modulo"), nullable=False
    )
