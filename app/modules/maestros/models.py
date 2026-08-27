from enum import Enum

from sqlalchemy import BigInteger, Boolean, Enum as SAEnum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TipoCalculoBeneficio(str, Enum):
    POR_EVENTO = "POR_EVENTO"
    POR_ANIO = "POR_ANIO"
    SIN_BENEFICIO = "SIN_BENEFICIO"


class Cargo(Base):
    __tablename__ = "cargo"

    id_cargo: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        index=True,
    )

    nombre_cargo: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )

    estado: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )


class Area(Base):
    __tablename__ = "area"

    id_area: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        index=True,
    )

    nombre_area: Mapped[str] = mapped_column(
        "nombre",
        String(100),
        nullable=False,
        unique=True,
    )

    descripcion: Mapped[str | None] = mapped_column(
        String(255),
    )

    estado: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )


class Beneficio(Base):
    __tablename__ = "beneficio"

    id_beneficio: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        index=True,
    )

    nombre: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        unique=True,
    )

    condicion: Mapped[str | None] = mapped_column(
        String(255),
    )

    tipo_calculo: Mapped[TipoCalculoBeneficio] = mapped_column(
        SAEnum(
            TipoCalculoBeneficio,
            name="beneficio_tipo_calculo_enum",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=TipoCalculoBeneficio.POR_EVENTO,
    )

    personas_por_asignacion: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    estado: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )