from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from scripts.check_delete_dependencies import (
    DependencyCheckError,
    check_delete_dependencies,
)


pytestmark = pytest.mark.asyncio


async def test_reporta_fila_hija_que_impide_el_borrado() -> None:
    schema = f"test_dependencies_{uuid4().hex}"
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.execute(
                text(
                    f'CREATE TABLE "{schema}".padre ('
                    "id_padre BIGINT PRIMARY KEY)"
                )
            )
            await connection.execute(
                text(
                    f'CREATE TABLE "{schema}".hija ('
                    "id_hija BIGINT PRIMARY KEY, "
                    "id_padre BIGINT NOT NULL, "
                    "CONSTRAINT fk_hija_padre FOREIGN KEY (id_padre) "
                    f'REFERENCES "{schema}".padre(id_padre))'
                )
            )
            await connection.execute(
                text(f'INSERT INTO "{schema}".padre (id_padre) VALUES (10)')
            )
            await connection.execute(
                text(
                    f'INSERT INTO "{schema}".hija (id_hija, id_padre) '
                    "VALUES (20, 10)"
                )
            )

            report = await connection.run_sync(
                lambda sync_connection: check_delete_dependencies(
                    sync_connection,
                    table_name="padre",
                    raw_value="10",
                    schema=schema,
                )
            )

        assert report.exists is True
        assert report.can_delete is False
        assert len(report.dependencies) == 1
        assert report.dependencies[0].table == "hija"
        assert report.dependencies[0].column == "id_padre"
        assert report.dependencies[0].rows == 1
        assert report.dependencies[0].on_delete == "NO ACTION"
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()


async def test_permite_borrado_si_no_hay_filas_hijas() -> None:
    schema = f"test_dependencies_{uuid4().hex}"
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.execute(
                text(
                    f'CREATE TABLE "{schema}".padre ('
                    "id_padre BIGINT PRIMARY KEY)"
                )
            )
            await connection.execute(
                text(f'INSERT INTO "{schema}".padre (id_padre) VALUES (10)')
            )

            report = await connection.run_sync(
                lambda sync_connection: check_delete_dependencies(
                    sync_connection,
                    table_name="padre",
                    raw_value="10",
                    schema=schema,
                )
            )

        assert report.exists is True
        assert report.can_delete is True
        assert report.dependencies == []
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()


async def test_rechaza_tabla_inexistente() -> None:
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as connection:
            with pytest.raises(DependencyCheckError, match="no existe"):
                await connection.run_sync(
                    lambda sync_connection: check_delete_dependencies(
                        sync_connection,
                        table_name="tabla_que_no_existe",
                        raw_value="1",
                    )
                )
    finally:
        await engine.dispose()
