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


class Categoria(Base):
    __tablename__ = "categoria"

    id_categoria: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre_categoria: Mapped[str] = mapped_column(
        String(120), nullable=False, unique=True
    )
    descripcion: Mapped[str | None] = mapped_column(String(255))
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DetalleCategoria(Base):
    __tablename__ = "detalle_categoria"
    __table_args__ = (
        UniqueConstraint(
            "id_grupo",
            "id_categoria",
            name="uq_detalle_categoria_grupo_categoria",
        ),
        UniqueConstraint(
            "id_detalle_categoria",
            "id_grupo",
            name="uq_detalle_categoria_id_grupo",
        ),
    )

    id_detalle_categoria: Mapped[int] = mapped_column(
        BigInteger, primary_key=True
    )
    id_grupo: Mapped[int] = mapped_column(
        ForeignKey("grupo.id_grupo"), nullable=False
    )
    id_categoria: Mapped[int] = mapped_column(
        ForeignKey("categoria.id_categoria"), nullable=False
    )
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
