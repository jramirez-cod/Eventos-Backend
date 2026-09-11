from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from scripts.migrate_eventos_schema import migrate_eventos_connection


pytestmark = pytest.mark.asyncio


async def test_migra_evento_y_programacion_legados_de_forma_idempotente() -> None:
    schema = f"test_eventos_migration_{uuid4().hex}"
    admin_engine = create_async_engine(settings.database_url)
    engine = None
    try:
        async with admin_engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))

        engine = create_async_engine(
            settings.database_url,
            connect_args={"options": f"-csearch_path={schema}"},
        )
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    CREATE TABLE area (
                        id_area BIGSERIAL PRIMARY KEY,
                        nombre VARCHAR(100) NOT NULL,
                        estado BOOLEAN NOT NULL DEFAULT TRUE
                    );
                    CREATE TABLE politica_evento (
                        id_politica_evento BIGSERIAL PRIMARY KEY,
                        fecha_inicio DATE NOT NULL,
                        fecha_fin DATE NOT NULL
                    );
                    CREATE TABLE evento (
                        id_evento BIGSERIAL PRIMARY KEY,
                        nombre_evento VARCHAR(200) NOT NULL,
                        descripcion TEXT,
                        fecha_inicio DATE NOT NULL,
                        fecha_fin DATE NOT NULL,
                        aforo INTEGER,
                        estado VARCHAR(20) NOT NULL,
                        creado_por BIGINT NOT NULL
                    );
                    CREATE TABLE programacion_evento (
                        id_programacion_evento BIGSERIAL PRIMARY KEY,
                        id_evento BIGINT NOT NULL REFERENCES evento(id_evento),
                        modalidad VARCHAR(20) NOT NULL,
                        estado BOOLEAN NOT NULL DEFAULT TRUE,
                        CONSTRAINT uq_programacion_evento_evento UNIQUE (id_evento)
                    );
                    INSERT INTO area (nombre) VALUES ('Eventos');
                    INSERT INTO evento (
                        nombre_evento, fecha_inicio, fecha_fin, estado, creado_por
                    ) VALUES ('Evento legado', '2026-10-01', '2026-10-03', 'ABIERTO', 1);
                    INSERT INTO programacion_evento (id_evento, modalidad)
                    VALUES (1, 'PRESENCIAL');
                    """
                )
            )

            first = await migrate_eventos_connection(conn)
            second = await migrate_eventos_connection(conn)

            assert first.migrated_events == 1
            assert first.default_area_id == 1
            assert first.schema_was_legacy is True
            assert second.migrated_events == 0
            assert second.schema_was_legacy is False

            evento = (
                await conn.execute(
                    text(
                        """
                        SELECT e.id_area, p.fecha_inicio, p.fecha_fin,
                               e.fecha_inicio AS fecha_inicio_legada
                        FROM evento e
                        JOIN politica_evento p
                          ON p.id_politica_evento = e.id_politica_evento
                        WHERE e.id_evento = 1
                        """
                    )
                )
            ).one()
            assert evento.id_area == 1
            assert str(evento.fecha_inicio) == "2026-10-01"
            assert str(evento.fecha_fin) == "2026-10-03"
            assert str(evento.fecha_inicio_legada) == "2026-10-01"

            programacion = (
                await conn.execute(
                    text(
                        """
                        SELECT estado::text AS estado,
                               pg_typeof(estado)::text AS tipo
                        FROM programacion_evento
                        WHERE id_programacion_evento = 1
                        """
                    )
                )
            ).one()
            assert programacion.estado == "ABIERTO"
            assert programacion.tipo == "programacion_estado_enum"

            unique_constraint = await conn.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM pg_constraint
                    WHERE conrelid = 'programacion_evento'::regclass
                      AND conname = 'uq_programacion_evento_evento'
                    """
                )
            )
            assert unique_constraint == 0
    finally:
        if engine is not None:
            await engine.dispose()
        async with admin_engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin_engine.dispose()
