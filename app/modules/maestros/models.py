from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


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