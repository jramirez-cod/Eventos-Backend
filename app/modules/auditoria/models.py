from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Auditoria(Base):
    __tablename__ = "auditoria"

    id_auditoria: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    id_usuario: Mapped[int | None] = mapped_column(ForeignKey("usuario.id_usuario"))
    id_modulo: Mapped[int | None] = mapped_column(ForeignKey("modulo.id_modulo"))
    origen: Mapped[str] = mapped_column(String(20), nullable=False, default="USUARIO")
    accion: Mapped[str] = mapped_column(String(60), nullable=False)
    entidad: Mapped[str] = mapped_column(String(100), nullable=False)
    id_entidad: Mapped[str | None] = mapped_column("entidad_id", String(100))
    valor_anterior: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    valor_nuevo: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    motivo: Mapped[str | None] = mapped_column(Text)
    ip_origen: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
