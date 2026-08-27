from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.modules.auditoria.models import Auditoria
from test.modules.eventos.conftest import crear_evento_http, seed_event_actor


pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("flyer.jpg", "image/jpeg"),
        ("flyer.jpeg", "image/jpeg"),
        ("flyer.png", "image/png"),
    ],
)
async def test_adjuntar_flyer_valido(
    client, session_factory, filename: str, content_type: str
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    response = await client.put(
        f"/api/v1/eventos/{evento['id_evento']}/flyer",
        headers=headers,
        files={"flyer": (filename, b"imagen-valida", content_type)},
    )
    assert response.status_code == 200, response.text
    flyer_url = response.json()["flyer_url"]
    stored = Path(settings.event_flyer_upload_dir) / Path(flyer_url).name
    assert stored.read_bytes() == b"imagen-valida"


async def test_archivo_no_permitido_es_rechazado(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    response = await client.put(
        f"/api/v1/eventos/{evento['id_evento']}/flyer",
        headers=headers,
        files={"flyer": ("flyer.pdf", b"contenido", "application/pdf")},
    )
    assert response.status_code == 400


async def test_mime_no_coincidente_es_rechazado(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    response = await client.put(
        f"/api/v1/eventos/{evento['id_evento']}/flyer",
        headers=headers,
        files={"flyer": ("flyer.png", b"contenido", "image/jpeg")},
    )
    assert response.status_code == 400


async def test_reemplazar_flyer_elimina_anterior_y_audita(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    url = f"/api/v1/eventos/{evento['id_evento']}/flyer"
    first = await client.put(
        url,
        headers=headers,
        files={"flyer": ("first.png", b"primero", "image/png")},
    )
    first_path = Path(settings.event_flyer_upload_dir) / Path(
        first.json()["flyer_url"]
    ).name
    second = await client.put(
        url,
        headers=headers,
        files={"flyer": ("second.jpg", b"segundo", "image/jpeg")},
    )
    second_path = Path(settings.event_flyer_upload_dir) / Path(
        second.json()["flyer_url"]
    ).name

    assert second.status_code == 200
    assert not first_path.exists()
    assert second_path.read_bytes() == b"segundo"
    async with session_factory() as session:
        actions = list(
            (
                await session.scalars(
                    select(Auditoria.accion).where(
                        Auditoria.accion.in_(
                            [
                                "ADJUNTAR_FLYER_EVENTO",
                                "REEMPLAZAR_FLYER_EVENTO",
                            ]
                        )
                    )
                )
            ).all()
        )
        assert actions == ["ADJUNTAR_FLYER_EVENTO", "REEMPLAZAR_FLYER_EVENTO"]


async def test_descargar_flyer_requiere_permiso(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)
    upload = await client.put(
        f"/api/v1/eventos/{evento['id_evento']}/flyer",
        headers=headers,
        files={"flyer": ("flyer.png", b"contenido", "image/png")},
    )
    flyer_url = upload.json()["flyer_url"]
    unauthorized = await client.get(flyer_url)
    authorized = await client.get(flyer_url, headers=headers)
    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.content == b"contenido"
