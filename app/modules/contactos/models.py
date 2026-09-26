from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Contacto(Base):
    __tablename__ = "contacto"

    __table_args__ = (
        CheckConstraint(
            "genero IN ('M', 'F', 'OTRO')",
            name="ck_contacto_genero",
        ),
        # Regla de negocio: a lo sumo un contacto principal por empresa. La
        # lógica ya demota al anterior antes de promover al nuevo; el índice
        # la vuelve imposible de violar (concurrencia, scripts, SQL directo).
        Index(
            "uq_contacto_principal_por_empresa",
            "id_empresa",
            unique=True,
            postgresql_where=text("es_contacto_principal"),
            sqlite_where=text("es_contacto_principal"),
        ),
    )

    id_contacto: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        index=True,
    )

    id_empresa: Mapped[int] = mapped_column(
        ForeignKey("empresa.id_empresa"),
        nullable=False,
        index=True,
    )

    id_cargo: Mapped[int | None] = mapped_column(
        ForeignKey("cargo.id_cargo"),
        nullable=True,
        index=True,
    )

    id_tipo_documento: Mapped[int | None] = mapped_column(
        ForeignKey("tipo_documento.id_tipo_documento"),
        nullable=True,
    )

    numero_documento: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        unique=True,
        index=True,
    )

    apellidos: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    nombres: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    genero: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    celular: Mapped[str | None] = mapped_column(
        String(20),
    )

    correo: Mapped[str | None] = mapped_column(
        String(254),
    )

    alias: Mapped[str | None] = mapped_column(
        String(120),
    )

    es_contacto_principal: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    estado: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @property
    def nombre_completo(self) -> str:
        return f"{self.apellidos} {self.nombres}".strip()

class ContactoHistorialEmpresa(Base):
    __tablename__ = "contacto_historial_empresa"

    id_historial: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        index=True,
    )

    id_contacto: Mapped[int] = mapped_column(
        ForeignKey("contacto.id_contacto"),
        nullable=False,
        index=True,
    )

    id_empresa: Mapped[int] = mapped_column(
        ForeignKey("empresa.id_empresa"),
        nullable=False,
        index=True,
    )

    id_usuario_cambio: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id_usuario"),
        nullable=True,
    )

    fecha_inicio: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    fecha_fin: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    motivo: Mapped[str | None] = mapped_column(
        Text,
    )