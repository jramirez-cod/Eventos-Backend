from sqlalchemy import BigInteger, Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Categoria(Base):
    __tablename__ = "categoria"

    id_categoria: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    nombre_categoria: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True
    )
    descripcion: Mapped[str | None] = mapped_column(String(255))
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class DetalleCategoria(Base):
    __tablename__ = "detalle_categoria"
    __table_args__ = (
        UniqueConstraint(
            "id_grupo",
            "id_categoria",
            name="uq_detalle_categoria_grupo_categoria",
        ),
    )

    id_detalle_categoria: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, index=True
    )
    id_grupo: Mapped[int] = mapped_column(
        ForeignKey("grupo.id_grupo"), nullable=False
    )
    id_categoria: Mapped[int] = mapped_column(
        ForeignKey("categoria.id_categoria"), nullable=False
    )
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
