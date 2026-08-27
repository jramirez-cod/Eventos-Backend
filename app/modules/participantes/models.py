from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EventoEmpresa(Base):
    __tablename__ = "evento_empresa"
    __table_args__ = (
        UniqueConstraint(
            "id_programacion_evento",
            "id_empresa",
            name="uq_evento_empresa_programacion_empresa",
        ),
    )

    id_evento_empresa: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True
    )
    id_programacion_evento: Mapped[int] = mapped_column(
        ForeignKey(
            "programacion_evento.id_programacion_evento", ondelete="CASCADE"
        ),
        nullable=False,
        index=True,
    )
    id_empresa: Mapped[int] = mapped_column(
        ForeignKey("empresa.id_empresa"), nullable=False, index=True
    )
    id_contacto_principal: Mapped[int | None] = mapped_column(
        ForeignKey("contacto.id_contacto"), index=True
    )
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class EventoContacto(Base):
    __tablename__ = "evento_contacto"
    __table_args__ = (
        UniqueConstraint(
            "id_programacion_evento",
            "id_contacto",
            name="uq_evento_contacto_programacion_contacto",
        ),
    )

    id_evento_contacto: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True
    )
    id_programacion_evento: Mapped[int] = mapped_column(
        ForeignKey(
            "programacion_evento.id_programacion_evento", ondelete="CASCADE"
        ),
        nullable=False,
        index=True,
    )
    id_contacto: Mapped[int | None] = mapped_column(
        ForeignKey("contacto.id_contacto"), index=True
    )
    id_empresa: Mapped[int] = mapped_column(
        ForeignKey("empresa.id_empresa"), nullable=False, index=True
    )
    invitado_nombres: Mapped[str | None] = mapped_column(String(120))
    invitado_apellidos: Mapped[str | None] = mapped_column(String(120))
    invitado_numero_documento: Mapped[str | None] = mapped_column(String(50))
    invitado_correo: Mapped[str | None] = mapped_column(String(254))
    invitado_celular: Mapped[str | None] = mapped_column(String(20))
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    requiere_coordinacion: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    asistencia_evento: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    hora_ingreso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    credencial_impresa: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )


class AsignacionBeneficio(Base):
    __tablename__ = "asignacion_beneficio"
    __table_args__ = (
        UniqueConstraint(
            "id_evento_contacto",
            name="uq_asignacion_beneficio_evento_contacto",
        ),
    )

    id_asignacion_beneficio: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True
    )
    id_evento_contacto: Mapped[int] = mapped_column(
        ForeignKey("evento_contacto.id_evento_contacto", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    id_beneficio: Mapped[int] = mapped_column(
        ForeignKey("beneficio.id_beneficio"), nullable=False, index=True
    )
    fecha_asignacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    codigo_grupo: Mapped[str | None] = mapped_column(String(64), index=True)


class ParticipanteQr(Base):
    __tablename__ = "participante_qr"
    __table_args__ = (
        UniqueConstraint(
            "id_evento_contacto",
            name="uq_participante_qr_evento_contacto",
        ),
    )

    id_participante_qr: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True
    )
    id_evento_contacto: Mapped[int] = mapped_column(
        ForeignKey("evento_contacto.id_evento_contacto", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    codigo_seguro: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    fecha_generacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    fecha_envio: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CodigoAccesoPrincipal(Base):
    __tablename__ = "codigo_acceso_principal"

    id_codigo_acceso_principal: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True
    )
    id_evento_empresa: Mapped[int] = mapped_column(
        ForeignKey("evento_empresa.id_evento_empresa", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    codigo_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fecha_envio: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
