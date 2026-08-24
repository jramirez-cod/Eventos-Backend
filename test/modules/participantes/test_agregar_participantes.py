import pytest
from sqlalchemy import func, select

from app.modules.eventos.models import EventoEstado
from app.modules.participantes.models import Participante
from test.modules.contactos.conftest import create_contacto, create_empresa
from test.modules.participantes.conftest import participante_context


pytestmark = pytest.mark.asyncio


async def test_agrega_un_contacto_con_confirmacion_inicial(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers, evento, _, contacto, afiliacion = await participante_context(
            session, client
        )

    response = await client.post(
        f"/api/v1/participantes/eventos/{evento.id_evento}",
        headers=headers,
        json={
            "id_evento_empresa": afiliacion["id_evento_empresa"],
            "ids_contacto": [contacto.id_contacto],
        },
    )

    assert response.status_code == 201
    assert response.json()["created"] == 1
    assert response.json()["participantes"][0]["confirmacion"] == "SIN_RESPUESTA"


async def test_agrega_varios_contactos_atomicamente(client, session_factory) -> None:
    async with session_factory() as session:
        actor, headers, evento, empresa, contacto, afiliacion = await participante_context(
            session, client
        )
        otros = [
            await create_contacto(
                session,
                empresa=empresa,
                actor=actor,
                sequence=40_001 + index,
            )
            for index in range(2)
        ]
        await session.commit()

    ids = [contacto.id_contacto, *(item.id_contacto for item in otros)]
    response = await client.post(
        f"/api/v1/participantes/eventos/{evento.id_evento}",
        headers=headers,
        json={"id_evento_empresa": afiliacion["id_evento_empresa"], "ids_contacto": ids},
    )

    assert response.status_code == 201
    assert response.json()["created"] == 3
    assert {item["confirmacion"] for item in response.json()["participantes"]} == {
        "SIN_RESPUESTA"
    }


@pytest.mark.parametrize("estado", [EventoEstado.FINALIZADO, EventoEstado.INACTIVO])
async def test_no_agrega_contactos_a_evento_no_abierto(
    client, session_factory, estado
) -> None:
    async with session_factory() as session:
        _, headers, evento, _, contacto, afiliacion = await participante_context(
            session, client
        )
        evento.estado = estado
        await session.commit()

    response = await client.post(
        f"/api/v1/participantes/eventos/{evento.id_evento}",
        headers=headers,
        json={
            "id_evento_empresa": afiliacion["id_evento_empresa"],
            "ids_contacto": [contacto.id_contacto],
        },
    )
    assert response.status_code == 409


async def test_no_agrega_contacto_inactivo(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers, evento, _, contacto, afiliacion = await participante_context(
            session, client, contacto_estado=False
        )

    response = await client.post(
        f"/api/v1/participantes/eventos/{evento.id_evento}",
        headers=headers,
        json={
            "id_evento_empresa": afiliacion["id_evento_empresa"],
            "ids_contacto": [contacto.id_contacto],
        },
    )
    assert response.status_code == 409


async def test_no_agrega_contacto_de_otra_empresa(client, session_factory) -> None:
    async with session_factory() as session:
        actor, headers, evento, _, _, afiliacion = await participante_context(
            session, client
        )
        otra_empresa = await create_empresa(session, sequence=50_001)
        contacto_ajeno = await create_contacto(
            session, empresa=otra_empresa, actor=actor, sequence=50_001
        )
        await session.commit()

    response = await client.post(
        f"/api/v1/participantes/eventos/{evento.id_evento}",
        headers=headers,
        json={
            "id_evento_empresa": afiliacion["id_evento_empresa"],
            "ids_contacto": [contacto_ajeno.id_contacto],
        },
    )
    assert response.status_code == 409


async def test_lote_con_duplicado_no_crea_parcialmente(client, session_factory) -> None:
    async with session_factory() as session:
        actor, headers, evento, empresa, existente, afiliacion = await participante_context(
            session, client
        )
        nuevo = await create_contacto(
            session, empresa=empresa, actor=actor, sequence=60_001
        )
        await session.commit()

    url = f"/api/v1/participantes/eventos/{evento.id_evento}"
    first = await client.post(
        url,
        headers=headers,
        json={
            "id_evento_empresa": afiliacion["id_evento_empresa"],
            "ids_contacto": [existente.id_contacto],
        },
    )
    assert first.status_code == 201

    second = await client.post(
        url,
        headers=headers,
        json={
            "id_evento_empresa": afiliacion["id_evento_empresa"],
            "ids_contacto": [nuevo.id_contacto, existente.id_contacto],
        },
    )
    assert second.status_code == 409

    async with session_factory() as session:
        assert await session.scalar(
            select(func.count()).select_from(Participante)
        ) == 1
