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


class PoliticaEvento(Base):
    __tablename__ = "politica_evento"

    id_politica_evento: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True
    )
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)


class DetallePoliticaEvento(Base):
    __tablename__ = "detalle_politica_evento"

    id_detalle_politica_evento: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True
    )
    id_politica_evento: Mapped[int] = mapped_column(
        ForeignKey("politica_evento.id_politica_evento", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    id_beneficio: Mapped[int] = mapped_column(
        ForeignKey("beneficio.id_beneficio"), nullable=False, index=True
    )
    id_categoria: Mapped[int] = mapped_column(
        ForeignKey("categoria.id_categoria"), nullable=False, index=True
    )
    entradas_gratuitas: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )


class Evento(Base):
    __tablename__ = "evento"
    __table_args__ = (
        Index("ix_evento_nombre_evento", "nombre_evento"),
        Index("ix_evento_estado", "estado"),
    )

    id_evento: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    id_politica_evento: Mapped[int] = mapped_column(
        ForeignKey("politica_evento.id_politica_evento"), nullable=False, index=True
    )
    id_area: Mapped[int] = mapped_column(
        ForeignKey("area.id_area"), nullable=False, index=True
    )
    nombre_evento: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
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


class ProgramacionEvento(Base):
    __tablename__ = "programacion_evento"
    __table_args__ = (
        Index("ix_programacion_evento_modalidad", "modalidad"),
        Index("ix_programacion_evento_evento", "id_evento"),
        Index("ix_programacion_evento_estado", "estado"),
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
    estado: Mapped[EventoEstado] = mapped_column(
        SAEnum(
            EventoEstado,
            name="programacion_estado_enum",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=EventoEstado.ABIERTO,
    )


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


class ResponsableEvento(Base):
    __tablename__ = "responsable_evento"
    __table_args__ = (
        UniqueConstraint(
            "id_programacion_evento",
            "id_usuario",
            name="uq_responsable_evento_programacion_usuario",
        ),
    )

    id_responsable_evento: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True
    )
    id_programacion_evento: Mapped[int] = mapped_column(
        ForeignKey(
            "programacion_evento.id_programacion_evento", ondelete="CASCADE"
        ),
        nullable=False,
        index=True,
    )
    id_usuario: Mapped[int] = mapped_column(
        ForeignKey("usuario.id_usuario"), nullable=False, index=True
    )
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
