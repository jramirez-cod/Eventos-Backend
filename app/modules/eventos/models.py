from datetime import date, datetime, time
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EventoEstado(str, Enum):
    ABIERTO = "ABIERTO"
    FINALIZADO = "FINALIZADO"
    INACTIVO = "INACTIVO"


class EventoModalidad(str, Enum):
    PRESENCIAL = "PRESENCIAL"
    VIRTUAL = "VIRTUAL"
    HIBRIDO = "HIBRIDO"


class Lugar(Base):
    __tablename__ = "lugar"

    id_lugar: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    pais: Mapped[str | None] = mapped_column(String(100))
    provincia: Mapped[str | None] = mapped_column(String(100))
    distrito: Mapped[str | None] = mapped_column(String(100))
    direccion: Mapped[str | None] = mapped_column(String(255))
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Evento(Base):
    __tablename__ = "evento"
    __table_args__ = (
        CheckConstraint("aforo IS NULL OR aforo >= 0", name="ck_evento_aforo"),
        CheckConstraint("fecha_fin >= fecha_inicio", name="ck_evento_fechas"),
        Index("ix_evento_nombre_evento", "nombre_evento"),
        Index("ix_evento_fecha_inicio", "fecha_inicio"),
        Index("ix_evento_fecha_fin", "fecha_fin"),
        Index("ix_evento_estado", "estado"),
    )

    id_evento: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    nombre_evento: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    aforo: Mapped[int | None] = mapped_column(Integer)
    flyer_url: Mapped[str | None] = mapped_column(String(500))
    estado: Mapped[EventoEstado] = mapped_column(
        SAEnum(
            EventoEstado,
            name="evento_estado_enum",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=EventoEstado.ABIERTO,
    )
    creado_por: Mapped[int] = mapped_column(
        ForeignKey("usuario.id_usuario"), nullable=False, index=True
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


class ProgramacionEvento(Base):
    __tablename__ = "programacion_evento"
    __table_args__ = (
        UniqueConstraint("id_evento", name="uq_programacion_evento_evento"),
        Index("ix_programacion_evento_modalidad", "modalidad"),
    )

    id_programacion_evento: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True
    )
    id_evento: Mapped[int] = mapped_column(
        ForeignKey("evento.id_evento", ondelete="CASCADE"), nullable=False
    )
    id_lugar: Mapped[int | None] = mapped_column(ForeignKey("lugar.id_lugar"))
    modalidad: Mapped[EventoModalidad] = mapped_column(
        SAEnum(
            EventoModalidad,
            name="evento_modalidad_enum",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    enlace_general: Mapped[str | None] = mapped_column(String(500))
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class DetalleProgramacionEvento(Base):
    __tablename__ = "detalle_programacion_evento"
    __table_args__ = (
        UniqueConstraint(
            "id_programacion_evento",
            "fecha",
            name="uq_detalle_programacion_evento_fecha",
        ),
        CheckConstraint(
            "hora_fin IS NULL OR hora_fin > hora_inicio",
            name="ck_detalle_programacion_horas",
        ),
        Index("ix_detalle_programacion_fecha", "fecha"),
    )

    id_detalle_programacion: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True
    )
    id_programacion_evento: Mapped[int] = mapped_column(
        ForeignKey(
            "programacion_evento.id_programacion_evento", ondelete="CASCADE"
        ),
        nullable=False,
        index=True,
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    hora_inicio: Mapped[time] = mapped_column(Time, nullable=False)
    hora_fin: Mapped[time | None] = mapped_column(Time)
    enlace: Mapped[str | None] = mapped_column(String(500))
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
