from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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
)


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


def evento_payload(
    *,
    nombre: str = "Nexo Summit 2026",
    inicio_dias: int = 10,
    fin_dias: int = 12,
    modalidad: str = "PRESENCIAL",
) -> dict[str, object]:
    return {
        "nombre_evento": nombre,
        "descripcion": "Encuentro empresarial CODIP",
        "fecha_inicio": future_date(inicio_dias),
        "fecha_fin": future_date(fin_dias),
        "aforo": 250,
        "modalidad": modalidad,
        "enlace_general": None,
        "lugar": {
            "pais": "Perú",
            "provincia": "Lima",
            "distrito": "Miraflores",
            "direccion": "Av. Principal 123",
        },
        "hora_inicio": "09:00:00",
        "hora_fin": "18:00:00",
    }


async def crear_evento_http(
    client: AsyncClient,
    headers: dict[str, str],
    **payload_overrides: object,
) -> dict[str, object]:
    payload = evento_payload()
    payload.update(payload_overrides)
    response = await client.post("/api/v1/eventos", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


__all__ = [
    "EVENT_PERMISSIONS",
    "crear_evento_http",
    "evento_payload",
    "future_date",
    "seed_event_actor",
]
