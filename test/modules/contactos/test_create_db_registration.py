import pytest
from sqlalchemy import text

from scripts.create_db import Base


def test_create_db_registra_metadata_de_maestros_y_contactos() -> None:
    assert {"cargo", "area", "contacto", "contacto_historial_empresa"} <= set(
        Base.metadata.tables
    )


@pytest.mark.asyncio
async def test_create_all_crea_tablas_de_maestros_y_contactos(
    session_factory,
) -> None:
    async with session_factory() as session:
        for table_name in (
            "cargo",
            "area",
            "contacto",
            "contacto_historial_empresa",
        ):
            table = await session.scalar(
                text("SELECT to_regclass(:table_name)"),
                {"table_name": table_name},
            )
            assert table == table_name
