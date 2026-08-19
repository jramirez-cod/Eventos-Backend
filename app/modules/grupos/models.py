from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Grupo(Base):
    __tablename__ = "grupo"

    id_grupo: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=False
    )
    nombre_grupo: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True
    )
    descripcion: Mapped[str | None] = mapped_column(String(255))
    estado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
