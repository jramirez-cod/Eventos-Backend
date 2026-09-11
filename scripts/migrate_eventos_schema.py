"""Migra de forma idempotente el esquema legado de Eventos al modelo actual.

Este script no se ejecuta durante el arranque de FastAPI. Debe invocarse de
forma explicita sobre una base existente creada antes de la normalizacion de
Evento/PoliticaEvento y de los estados de ProgramacionEvento.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402


@dataclass(frozen=True, slots=True)
class MigrationResult:
    migrated_events: int
    default_area_id: int | None
    schema_was_legacy: bool


async def _columns(conn: AsyncConnection, table_name: str) -> dict[str, str]:
    rows = (
        await conn.execute(
            text(
                """
                SELECT column_name, udt_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = :table_name
                """
            ),
            {"table_name": table_name},
        )
    ).all()
    return {str(row.column_name): str(row.udt_name) for row in rows}


async def _resolve_default_area(
    conn: AsyncConnection, requested_area_id: int | None
) -> int:
    if requested_area_id is not None:
        exists = await conn.scalar(
            text("SELECT EXISTS (SELECT 1 FROM area WHERE id_area = :id_area)"),
            {"id_area": requested_area_id},
        )
        if not exists:
            raise RuntimeError(
                f"El area indicada ({requested_area_id}) no existe en la base de datos."
            )
        return requested_area_id

    area_ids = list(
        (
            await conn.scalars(
                text("SELECT id_area FROM area ORDER BY id_area LIMIT 2")
            )
        ).all()
    )
    if len(area_ids) != 1:
        raise RuntimeError(
            "Los eventos legados no registran area. Indique --default-area-id "
            "cuando la base no tenga exactamente una area disponible."
        )
    return int(area_ids[0])


async def _migrate_legacy_eventos(
    conn: AsyncConnection, *, default_area_id: int | None
) -> tuple[int, int | None, bool]:
    columns = await _columns(conn, "evento")
    if not columns:
        raise RuntimeError("No existe la tabla evento en el esquema activo.")

    required = {"id_politica_evento", "id_area"}
    missing = required - columns.keys()
    schema_was_legacy = bool(missing)
    if missing and not {"fecha_inicio", "fecha_fin"}.issubset(columns):
        raise RuntimeError(
            "La tabla evento no coincide con el esquema legado ni con el actual. "
            f"Faltan columnas: {', '.join(sorted(missing))}."
        )

    pending = int(
        await conn.scalar(text("SELECT count(*) FROM evento")) or 0
    ) if schema_was_legacy else int(
        await conn.scalar(
            text("SELECT count(*) FROM evento WHERE id_politica_evento IS NULL")
        )
        or 0
    )
    resolved_area_id: int | None = None
    if pending:
        resolved_area_id = await _resolve_default_area(conn, default_area_id)

    if "id_politica_evento" not in columns:
        await conn.execute(
            text("ALTER TABLE evento ADD COLUMN id_politica_evento BIGINT")
        )
    if "id_area" not in columns:
        await conn.execute(text("ALTER TABLE evento ADD COLUMN id_area BIGINT"))

    migrated = 0
    if pending:
        legacy_rows = (
            await conn.execute(
                text(
                    """
                    SELECT id_evento, fecha_inicio, fecha_fin, id_area,
                           id_politica_evento
                    FROM evento
                    WHERE id_politica_evento IS NULL
                    ORDER BY id_evento
                    FOR UPDATE
                    """
                )
            )
        ).all()
        for row in legacy_rows:
            policy_id = await conn.scalar(
                text(
                    """
                    INSERT INTO politica_evento (fecha_inicio, fecha_fin)
                    VALUES (:fecha_inicio, :fecha_fin)
                    RETURNING id_politica_evento
                    """
                ),
                {
                    "fecha_inicio": row.fecha_inicio,
                    "fecha_fin": row.fecha_fin,
                },
            )
            await conn.execute(
                text(
                    """
                    UPDATE evento
                    SET id_politica_evento = :policy_id,
                        id_area = COALESCE(id_area, :id_area)
                    WHERE id_evento = :id_evento
                    """
                ),
                {
                    "policy_id": policy_id,
                    "id_area": resolved_area_id,
                    "id_evento": row.id_evento,
                },
            )
            migrated += 1

    await conn.execute(
        text(
            """
            DO $migration$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'evento'::regclass
                      AND conname = 'evento_id_politica_evento_fkey'
                ) THEN
                    ALTER TABLE evento
                    ADD CONSTRAINT evento_id_politica_evento_fkey
                    FOREIGN KEY (id_politica_evento)
                    REFERENCES politica_evento(id_politica_evento);
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'evento'::regclass
                      AND conname = 'evento_id_area_fkey'
                ) THEN
                    ALTER TABLE evento
                    ADD CONSTRAINT evento_id_area_fkey
                    FOREIGN KEY (id_area) REFERENCES area(id_area);
                END IF;
            END
            $migration$;
            """
        )
    )
    await conn.execute(
        text(
            """
            ALTER TABLE evento
                ALTER COLUMN id_politica_evento SET NOT NULL,
                ALTER COLUMN id_area SET NOT NULL;
            CREATE INDEX IF NOT EXISTS ix_evento_id_politica_evento
                ON evento (id_politica_evento);
            CREATE INDEX IF NOT EXISTS ix_evento_id_area ON evento (id_area);
            """
        )
    )

    # Se conservan los datos legados, pero dejan de ser obligatorios para que
    # las nuevas inserciones usen PoliticaEvento y el usuario actor se audite.
    for legacy_column in ("fecha_inicio", "fecha_fin", "creado_por"):
        if legacy_column in columns:
            await conn.execute(
                text(
                    f"ALTER TABLE evento ALTER COLUMN {legacy_column} DROP NOT NULL"
                )
            )

    return migrated, resolved_area_id, schema_was_legacy


async def _migrate_programacion_estado(conn: AsyncConnection) -> None:
    columns = await _columns(conn, "programacion_evento")
    if not columns:
        raise RuntimeError("No existe la tabla programacion_evento.")

    estado_type = columns.get("estado")
    if estado_type == "bool":
        await conn.execute(
            text(
                """
                DO $migration$
                BEGIN
                    CREATE TYPE programacion_estado_enum AS ENUM
                        ('ABIERTO', 'FINALIZADO', 'INACTIVO');
                EXCEPTION
                    WHEN duplicate_object THEN NULL;
                END
                $migration$;

                ALTER TABLE programacion_evento
                    ALTER COLUMN estado DROP DEFAULT,
                    ALTER COLUMN estado TYPE programacion_estado_enum
                    USING (
                        CASE WHEN estado THEN 'ABIERTO' ELSE 'INACTIVO' END
                    )::programacion_estado_enum,
                    ALTER COLUMN estado SET DEFAULT 'ABIERTO',
                    ALTER COLUMN estado SET NOT NULL;
                """
            )
        )
    elif estado_type != "programacion_estado_enum":
        raise RuntimeError(
            "programacion_evento.estado tiene un tipo inesperado: "
            f"{estado_type!r}."
        )

    await conn.execute(
        text(
            """
            ALTER TABLE programacion_evento
                DROP CONSTRAINT IF EXISTS uq_programacion_evento_evento;
            CREATE INDEX IF NOT EXISTS ix_programacion_evento_evento
                ON programacion_evento (id_evento);
            CREATE INDEX IF NOT EXISTS ix_programacion_evento_estado
                ON programacion_evento (estado);
            """
        )
    )


async def migrate_eventos_connection(
    conn: AsyncConnection, *, default_area_id: int | None = None
) -> MigrationResult:
    await conn.execute(
        text(
            "SELECT pg_advisory_xact_lock(hashtext(" 
            "'eventos_codip_migrate_eventos_schema_v2'))"
        )
    )
    migrated, resolved_area, was_legacy = await _migrate_legacy_eventos(
        conn, default_area_id=default_area_id
    )
    await _migrate_programacion_estado(conn)
    return MigrationResult(
        migrated_events=migrated,
        default_area_id=resolved_area,
        schema_was_legacy=was_legacy,
    )


async def migrate(default_area_id: int | None = None) -> MigrationResult:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            return await migrate_eventos_connection(
                conn, default_area_id=default_area_id
            )
    finally:
        await engine.dispose()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migra una base con el esquema legado del modulo Eventos."
    )
    parser.add_argument(
        "--default-area-id",
        type=int,
        default=None,
        help=(
            "Area que se asignara a eventos legados. Es obligatorio cuando "
            "existe mas de una area en la base."
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    result = asyncio.run(migrate(default_area_id=args.default_area_id))
    print(
        "Migracion de Eventos completada: "
        f"eventos_migrados={result.migrated_events}, "
        f"area_asignada={result.default_area_id}, "
        f"esquema_legado={result.schema_was_legacy}."
    )
