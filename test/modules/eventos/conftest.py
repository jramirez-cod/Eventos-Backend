from datetime import datetime, timedelta
from itertools import count
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.categorias.models import Categoria
from app.modules.maestros.models import Area, Beneficio
from app.modules.usuarios.models import Usuario
from test.modules.usuarios.conftest import (
    auth_header,
    create_role,
    create_user,
    grant_permission,
)


EVENT_PERMISSIONS = (
    "CONSULTAR_EVENTO",
    "CREAR_EVENTO",
    "ACTUALIZAR_EVENTO",
    "CAMBIAR_ESTADO_EVENTO",
    "REABRIR_EVENTO",
    "ELIMINAR_EVENTO",
    "EXPORTAR_EVENTO",
    "CAMBIAR_ESTADO_PROGRAMACION",
    "REABRIR_PROGRAMACION",
)

_sequence = count(1)


def next_sequence() -> int:
    return next(_sequence)


@pytest.fixture(autouse=True)
def isolated_flyer_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings, "event_flyer_upload_dir", str(tmp_path / "event-flyers")
    )


async def seed_event_actor(
    session: AsyncSession,
    *,
    username: str = "actor.eventos",
    permissions: tuple[str, ...] = EVENT_PERMISSIONS,
) -> tuple[Usuario, dict[str, str]]:
    role = await create_role(session, f"Rol {username}")
    for permission in permissions:
        await grant_permission(
            session,
            role,
            permiso_nombre=permission,
            modulo_nombre="EVENTOS",
        )
    actor = await create_user(session, role, username=username)
    await session.commit()
    return actor, auth_header(actor)


def future_date(days: int) -> str:
    today = datetime.now(ZoneInfo("America/Lima")).date()
    return (today + timedelta(days=days)).isoformat()


async def create_evento_dependencies(
    session: AsyncSession, *, sequence: int | None = None
) -> tuple[Area, Beneficio, Categoria]:
    sequence = sequence or next_sequence()
    area = Area(nombre_area=f"Area Eventos {sequence}", estado=True)
    beneficio = Beneficio(nombre=f"Beneficio Eventos {sequence}", estado=True)
    categoria = Categoria(nombre_categoria=f"Categoria Eventos {sequence}", estado=True)
    session.add_all([area, beneficio, categoria])
    await session.flush()
    return area, beneficio, categoria


def politica_payload(
    *,
    id_beneficio: int,
    id_categoria: int,
    inicio_dias: int = 5,
    fin_dias: int = 60,
    entradas_gratuitas: int = 2,
) -> dict[str, object]:
    return {
        "fecha_inicio": future_date(inicio_dias),
        "fecha_fin": future_date(fin_dias),
        "detalles": [
            {
                "id_beneficio": id_beneficio,
                "id_categoria": id_categoria,
                "entradas_gratuitas": entradas_gratuitas,
            }
        ],
    }


def evento_payload(
    *,
    id_area: int,
    id_beneficio: int,
    id_categoria: int,
    nombre: str = "Nexo Summit 2026",
) -> dict[str, object]:
    return {
        "nombre_evento": nombre,
        "descripcion": "Encuentro empresarial CODIP",
        "id_area": id_area,
        "politica": politica_payload(
            id_beneficio=id_beneficio, id_categoria=id_categoria
        ),
    }


async def crear_evento_http(
    client: AsyncClient,
    headers: dict[str, str],
    session_factory,
    *,
    politica_fecha_inicio: str | None = None,
    politica_fecha_fin: str | None = None,
    **payload_overrides: object,
) -> dict[str, object]:
    async with session_factory() as session:
        area, beneficio, categoria = await create_evento_dependencies(session)
        await session.commit()
        id_area, id_beneficio, id_categoria = (
            area.id_area,
            beneficio.id_beneficio,
            categoria.id_categoria,
        )
    payload = evento_payload(
        id_area=id_area, id_beneficio=id_beneficio, id_categoria=id_categoria
    )
    if politica_fecha_inicio is not None:
        payload["politica"]["fecha_inicio"] = politica_fecha_inicio
    if politica_fecha_fin is not None:
        payload["politica"]["fecha_fin"] = politica_fecha_fin
    payload.update(payload_overrides)
    response = await client.post("/api/v1/eventos", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def programacion_payload(
    *,
    modalidad: str = "PRESENCIAL",
    inicio_dias: int = 10,
    fin_dias: int = 12,
    incluir_lugar: bool = True,
    enlace_general: str | None = None,
) -> dict[str, object]:
    dias = [
        {
            "fecha": future_date(offset),
            "hora_inicio": "09:00:00",
            "hora_fin": "18:00:00",
        }
        for offset in range(inicio_dias, fin_dias + 1)
    ]
    payload: dict[str, object] = {
        "modalidad": modalidad,
        "enlace_general": enlace_general,
        "dias": dias,
    }
    if incluir_lugar:
        payload["lugar"] = {
            "pais": "Perú",
            "provincia": "Lima",
            "distrito": "Miraflores",
            "direccion": "Av. Principal 123",
        }
    else:
        payload["lugar"] = None
    return payload


async def crear_programacion_http(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    id_evento: int,
    modalidad: str = "PRESENCIAL",
    inicio_dias: int = 10,
    fin_dias: int = 12,
    incluir_lugar: bool = True,
    enlace_general: str | None = None,
    **payload_overrides: object,
) -> dict[str, object]:
    payload = programacion_payload(
        modalidad=modalidad,
        inicio_dias=inicio_dias,
        fin_dias=fin_dias,
        incluir_lugar=incluir_lugar,
        enlace_general=enlace_general,
    )
    payload.update(payload_overrides)
    response = await client.post(
        f"/api/v1/eventos/{id_evento}/programaciones",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


__all__ = [
    "EVENT_PERMISSIONS",
    "create_evento_dependencies",
    "crear_evento_http",
    "crear_programacion_http",
    "evento_payload",
    "future_date",
    "next_sequence",
    "politica_payload",
    "programacion_payload",
    "seed_event_actor",
]
