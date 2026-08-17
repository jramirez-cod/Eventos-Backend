from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Grupo(Base):
    __tablename__ = "grupo"

    id_grupo: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre_grupo: Mapped[str] = mapped_column(
        String(120), nullable=False, unique=True
    )
    descripcion: Mapped[str | None] = mapped_column(String(255))
    requiere_categoria: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
