from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Empresa(Base):
    __tablename__ = "empresa"
    __table_args__ = (
        CheckConstraint("ruc ~ '^[0-9]{11}$'", name="ck_empresa_ruc"),
    )

    id_empresa: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    id_detalle_categoria: Mapped[int] = mapped_column(
        ForeignKey("detalle_categoria.id_detalle_categoria"), nullable=False
    )
    nombre_empresa: Mapped[str] = mapped_column(String(180), nullable=False)
    razon_social: Mapped[str | None] = mapped_column(String(250))
    nombre_comercial: Mapped[str | None] = mapped_column(String(180))
    ruc: Mapped[str] = mapped_column(String(11), nullable=False, unique=True)
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class EmpresaHistorialClasificacion(Base):
    __tablename__ = "empresa_historial_clasificacion"

    id_historial: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    id_empresa: Mapped[int] = mapped_column(
        ForeignKey("empresa.id_empresa"), nullable=False, index=True
    )
    id_detalle_categoria: Mapped[int] = mapped_column(
        ForeignKey("detalle_categoria.id_detalle_categoria"), nullable=False
    )
    fecha_inicio: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    fecha_fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
