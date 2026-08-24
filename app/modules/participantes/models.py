from datetime import datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConfirmacionParticipante(str, Enum):
    SIN_RESPUESTA = "SIN_RESPUESTA"
    SI = "SI"
    NO = "NO"


class EventoEmpresa(Base):
    __tablename__ = "evento_empresa"
    __table_args__ = (
        UniqueConstraint(
            "id_evento", "id_empresa", name="uq_evento_empresa_evento_empresa"
        ),
        UniqueConstraint(
            "id_evento_empresa",
            "id_evento",
            name="uq_evento_empresa_id_evento",
        ),
        Index("ix_evento_empresa_empresa", "id_empresa"),
    )

    id_evento_empresa: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True
    )
    id_evento: Mapped[int] = mapped_column(
        ForeignKey("evento.id_evento", ondelete="CASCADE"), nullable=False
    )
    id_empresa: Mapped[int] = mapped_column(
        ForeignKey("empresa.id_empresa"), nullable=False
    )
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    creado_por: Mapped[int] = mapped_column(
        ForeignKey("usuario.id_usuario"), nullable=False
    )


class Participante(Base):
    __tablename__ = "participante"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id_evento_empresa", "id_evento"],
            ["evento_empresa.id_evento_empresa", "evento_empresa.id_evento"],
            name="fk_participante_evento_empresa_evento",
        ),
        UniqueConstraint(
            "id_evento", "id_contacto", name="uq_participante_evento_contacto"
        ),
        Index("ix_participante_evento_empresa", "id_evento_empresa"),
        Index("ix_participante_contacto", "id_contacto"),
        Index("ix_participante_confirmacion", "confirmacion"),
    )

    id_participante: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True
    )
    id_evento_empresa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    id_evento: Mapped[int] = mapped_column(
        ForeignKey("evento.id_evento"), nullable=False
    )
    id_contacto: Mapped[int] = mapped_column(
        ForeignKey("contacto.id_contacto"), nullable=False
    )
    confirmacion: Mapped[ConfirmacionParticipante] = mapped_column(
        SAEnum(
            ConfirmacionParticipante,
            name="participante_confirmacion_enum",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=ConfirmacionParticipante.SIN_RESPUESTA,
    )
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    creado_por: Mapped[int] = mapped_column(
        ForeignKey("usuario.id_usuario"), nullable=False
    )
