from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CorreoConfiguracionGlobal(Base):
    __tablename__ = "correo_configuracion_global"

    id_configuracion: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True
    )
    codigo: Mapped[str] = mapped_column(
        String(30), nullable=False, unique=True, default="GLOBAL"
    )
    id_usuario_emisor: Mapped[int] = mapped_column(
        ForeignKey("usuario.id_usuario"), nullable=False
    )
    nombre_remitente: Mapped[str] = mapped_column(String(120), nullable=False)
    reply_to: Mapped[str | None] = mapped_column(String(254))
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    actualizado_por: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id_usuario")
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CorreoPlantilla(Base):
    __tablename__ = "correo_plantilla"

    id_plantilla: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    codigo: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    asunto: Mapped[str] = mapped_column(String(255), nullable=False)
    cuerpo_html: Mapped[str] = mapped_column(Text, nullable=False)
    cuerpo_texto: Mapped[str] = mapped_column(Text, nullable=False)
    variables_permitidas: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    version_actual: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    actualizado_por: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id_usuario")
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CorreoPlantillaHistorial(Base):
    __tablename__ = "correo_plantilla_historial"
    __table_args__ = (
        UniqueConstraint(
            "id_plantilla", "version", name="uq_correo_plantilla_historial_version"
        ),
    )

    id_historial: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    id_plantilla: Mapped[int] = mapped_column(
        ForeignKey("correo_plantilla.id_plantilla", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    asunto: Mapped[str] = mapped_column(String(255), nullable=False)
    cuerpo_html: Mapped[str] = mapped_column(Text, nullable=False)
    cuerpo_texto: Mapped[str] = mapped_column(Text, nullable=False)
    motivo: Mapped[str | None] = mapped_column(String(255))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id_usuario"))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CorreoEnvio(Base):
    __tablename__ = "correo_envio"

    id_envio: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    id_plantilla: Mapped[int | None] = mapped_column(
        ForeignKey("correo_plantilla.id_plantilla", ondelete="RESTRICT"), index=True
    )
    version_plantilla: Mapped[int | None] = mapped_column(Integer)
    id_usuario_emisor: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id_usuario")
    )
    destinatario: Mapped[str] = mapped_column(String(254), nullable=False)
    asunto: Mapped[str] = mapped_column(String(255), nullable=False)
    entidad_origen: Mapped[str | None] = mapped_column(String(80))
    entidad_id: Mapped[str | None] = mapped_column(String(100))
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    intentos: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    error_detalle: Mapped[str | None] = mapped_column(String(500))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    enviado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

