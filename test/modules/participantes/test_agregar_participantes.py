import pytest
from sqlalchemy import func, select

from app.modules.eventos.models import Evento, EventoEstado, ProgramacionEvento
from app.modules.participantes.models import EventoContacto
from test.modules.contactos.conftest import create_contacto, create_empresa
from test.modules.participantes.conftest import evento_contacto_context


pytestmark = pytest.mark.asyncio


async def test_agrega_un_contacto_con_confirmacion_inicial(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers, programacion, _, contacto, _ = await evento_contacto_context(
            session, client
        )

    response = await client.post(
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/evento-contactos",
        headers=headers,
        json={"ids_contacto": [contacto.id_contacto]},
    )

    assert response.status_code == 201
    assert response.json()["created"] == 1
    assert response.json()["evento_contactos"][0]["estado"] is True


async def test_agrega_varios_contactos_atomicamente(client, session_factory) -> None:
    async with session_factory() as session:
        actor, headers, programacion, empresa, contacto, _ = (
            await evento_contacto_context(session, client)
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
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/evento-contactos",
        headers=headers,
        json={"ids_contacto": ids},
    )

    assert response.status_code == 201
    assert response.json()["created"] == 3
    assert {
        item["estado"] for item in response.json()["evento_contactos"]
    } == {True}


@pytest.mark.parametrize("estado", [EventoEstado.FINALIZADO, EventoEstado.INACTIVO])
async def test_no_agrega_contactos_a_evento_no_abierto(
    client, session_factory, estado
) -> None:
    async with session_factory() as session:
        _, headers, programacion, _, contacto, _ = await evento_contacto_context(
            session, client
        )

    async with session_factory() as session:
        evento = await session.get(Evento, programacion.id_evento)
        evento.estado = estado
        await session.commit()

    response = await client.post(
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/evento-contactos",
        headers=headers,
        json={"ids_contacto": [contacto.id_contacto]},
    )
    assert response.status_code == 409


@pytest.mark.parametrize("estado", [EventoEstado.FINALIZADO, EventoEstado.INACTIVO])
async def test_no_agrega_contactos_a_programacion_no_abierta(
    client, session_factory, estado
) -> None:
    async with session_factory() as session:
        _, headers, programacion, _, contacto, _ = await evento_contacto_context(
            session, client
        )

    async with session_factory() as session:
        prog = await session.get(
            ProgramacionEvento, programacion.id_programacion_evento
        )
        prog.estado = estado
        await session.commit()

    response = await client.post(
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/evento-contactos",
        headers=headers,
        json={"ids_contacto": [contacto.id_contacto]},
    )
    assert response.status_code == 409


async def test_no_agrega_contacto_inactivo(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers, programacion, _, contacto, _ = await evento_contacto_context(
            session, client, contacto_estado=False
        )

    response = await client.post(
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/evento-contactos",
        headers=headers,
        json={"ids_contacto": [contacto.id_contacto]},
    )
    assert response.status_code == 409


async def test_no_agrega_contacto_de_empresa_no_afiliada(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers, programacion, _, _, _ = await evento_contacto_context(
            session, client
        )
        otra_empresa = await create_empresa(session, sequence=50_001)
        contacto_ajeno = await create_contacto(
            session, empresa=otra_empresa, actor=actor, sequence=50_001
        )
        await session.commit()

    response = await client.post(
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/evento-contactos",
        headers=headers,
        json={"ids_contacto": [contacto_ajeno.id_contacto]},
    )
    assert response.status_code == 409


async def test_lote_con_duplicado_no_crea_parcialmente(client, session_factory) -> None:
    async with session_factory() as session:
        actor, headers, programacion, empresa, existente, _ = (
            await evento_contacto_context(session, client)
        )
        nuevo = await create_contacto(
            session, empresa=empresa, actor=actor, sequence=60_001
        )
        await session.commit()

    url = (
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/evento-contactos"
    )
    first = await client.post(
        url,
        headers=headers,
        json={"ids_contacto": [existente.id_contacto]},
    )
    assert first.status_code == 201

    second = await client.post(
        url,
        headers=headers,
        json={"ids_contacto": [nuevo.id_contacto, existente.id_contacto]},
    )
    assert second.status_code == 409

    async with session_factory() as session:
        assert (
            await session.scalar(select(func.count()).select_from(EventoContacto))
            == 1
        )
