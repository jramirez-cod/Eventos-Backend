"""Comprueba dependencias FK antes de evaluar un borrado fisico.

La herramienta es de solo lectura: inspecciona el catalogo PostgreSQL y cuenta
las filas hijas que referencian el registro. No ejecuta DELETE ni instala
funciones en la base de datos.

.venv/bin/python scripts/check_delete_dependencies.py \
  --table grupo \
  --id 10 \
  --include-empty
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import MetaData, Table, func, inspect, select
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402


@dataclass(frozen=True, slots=True)
class ForeignKeyDependency:
    table: str
    column: str
    constraint: str | None
    on_delete: str
    rows: int


@dataclass(frozen=True, slots=True)
class DeleteDependencyReport:
    schema: str
    table: str
    primary_key: str
    value: Any
    exists: bool
    can_delete: bool
    dependencies: list[ForeignKeyDependency]


class DependencyCheckError(ValueError):
    pass


def check_delete_dependencies(
    connection: Connection,
    *,
    table_name: str,
    raw_value: str,
    schema: str | None = None,
    include_empty: bool = False,
) -> DeleteDependencyReport:
    """Genera un reporte para una tabla con clave primaria simple."""

    inspector = inspect(connection)
    selected_schema = schema or inspector.default_schema_name
    table_names = set(inspector.get_table_names(schema=selected_schema))
    if table_name not in table_names:
        raise DependencyCheckError(
            f"La tabla {selected_schema}.{table_name} no existe."
        )

    pk = inspector.get_pk_constraint(table_name, schema=selected_schema)
    primary_key_columns = pk.get("constrained_columns") or []
    if len(primary_key_columns) != 1:
        raise DependencyCheckError(
            "La herramienta solo admite tablas con una clave primaria simple."
        )

    metadata = MetaData()
    parent = Table(
        table_name,
        metadata,
        schema=selected_schema,
        autoload_with=connection,
    )
    primary_key_name = primary_key_columns[0]
    primary_key = parent.c[primary_key_name]
    value = _coerce_value(primary_key.type, raw_value)
    exists = bool(
        connection.scalar(
            select(func.count())
            .select_from(parent)
            .where(primary_key == value)
        )
    )

    dependencies: list[ForeignKeyDependency] = []
    for child_name in sorted(table_names):
        foreign_keys = inspector.get_foreign_keys(
            child_name,
            schema=selected_schema,
        )
        for foreign_key in foreign_keys:
            referred_schema = foreign_key.get("referred_schema") or selected_schema
            if (
                referred_schema != selected_schema
                or foreign_key.get("referred_table") != table_name
            ):
                continue

            referred_columns = foreign_key.get("referred_columns") or []
            constrained_columns = foreign_key.get("constrained_columns") or []
            if primary_key_name not in referred_columns:
                continue

            position = referred_columns.index(primary_key_name)
            child_column_name = constrained_columns[position]
            child = Table(
                child_name,
                metadata,
                schema=selected_schema,
                autoload_with=connection,
                extend_existing=True,
            )
            rows = int(
                connection.scalar(
                    select(func.count())
                    .select_from(child)
                    .where(child.c[child_column_name] == value)
                )
                or 0
            )
            if rows or include_empty:
                options = foreign_key.get("options") or {}
                dependencies.append(
                    ForeignKeyDependency(
                        table=child_name,
                        column=child_column_name,
                        constraint=foreign_key.get("name"),
                        on_delete=str(options.get("ondelete") or "NO ACTION"),
                        rows=rows,
                    )
                )

    return DeleteDependencyReport(
        schema=selected_schema,
        table=table_name,
        primary_key=primary_key_name,
        value=value,
        exists=exists,
        can_delete=exists and not any(item.rows for item in dependencies),
        dependencies=dependencies,
    )


def _coerce_value(column_type: Any, raw_value: str) -> Any:
    try:
        python_type = column_type.python_type
    except NotImplementedError:
        return raw_value

    if python_type is bool:
        normalized = raw_value.strip().lower()
        if normalized in {"true", "1"}:
            return True
        if normalized in {"false", "0"}:
            return False
        raise DependencyCheckError("El valor no es un booleano valido.")

    try:
        return python_type(raw_value)
    except (TypeError, ValueError) as exc:
        raise DependencyCheckError(
            f"El valor no es valido para la clave primaria ({python_type.__name__})."
        ) from exc


async def _run(args: argparse.Namespace) -> int:
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as connection:
            report = await connection.run_sync(
                lambda sync_connection: check_delete_dependencies(
                    sync_connection,
                    table_name=args.table,
                    raw_value=args.id,
                    schema=args.schema,
                    include_empty=args.include_empty,
                )
            )
    finally:
        await engine.dispose()

    print(json.dumps(asdict(report), ensure_ascii=False, indent=2, default=str))
    if not report.exists:
        return 1
    return 0 if report.can_delete else 2


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Informa si un registro tiene filas relacionadas mediante claves "
            "foraneas. No elimina ni modifica datos."
        )
    )
    parser.add_argument("--table", required=True, help="Tabla padre a comprobar.")
    parser.add_argument("--id", required=True, help="Valor de su clave primaria.")
    parser.add_argument(
        "--schema",
        help="Esquema PostgreSQL. Por defecto usa el esquema de la conexion.",
    )
    parser.add_argument(
        "--include-empty",
        action="store_true",
        help="Incluye relaciones FK que actualmente tienen cero filas.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(_run(_parse_args())))
    except DependencyCheckError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
