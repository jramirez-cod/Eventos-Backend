from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Empresa(Base):
    __tablename__ = "empresa"
    __table_args__ = (
        CheckConstraint("ruc ~ '^[0-9]{11}$'", name="ck_empresa_ruc"),
        ForeignKeyConstraint(
            ["id_detalle_categoria", "id_grupo"],
            [
                "detalle_categoria.id_detalle_categoria",
                "detalle_categoria.id_grupo",
            ],
            name="fk_empresa_detalle_categoria_grupo",
        ),
    )

    id_empresa: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    id_grupo: Mapped[int] = mapped_column(
        ForeignKey("grupo.id_grupo"), nullable=False
    )
    id_detalle_categoria: Mapped[int | None] = mapped_column(BigInteger)
    nombre_empresa: Mapped[str] = mapped_column(String(180), nullable=False)
    nombre_comercial: Mapped[str | None] = mapped_column(String(180))
    razon_social: Mapped[str] = mapped_column(String(250), nullable=False)
    ruc: Mapped[str] = mapped_column(String(11), nullable=False, unique=True)
    logo_url: Mapped[str | None] = mapped_column(Text)
    observaciones: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_por: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id_usuario")
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
