import pytest

from test.modules.contactos.conftest import create_contacto
from test.modules.participantes.conftest import evento_contacto_context


pytestmark = pytest.mark.asyncio


async def test_lista_empresas_afiliadas_con_contexto(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers, programacion, empresa, _, afiliacion = (
            await evento_contacto_context(session, client)
        )

    response = await client.get(
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/empresas",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json() == [afiliacion]
    assert response.json()[0]["nombre_empresa"] == empresa.nombre_empresa


async def test_lista_filtra_busca_y_pagina_evento_contactos(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers, programacion, empresa, contacto, _ = (
            await evento_contacto_context(session, client)
        )
        otro = await create_contacto(
            session, empresa=empresa, actor=actor, sequence=70_001
        )
        otro.nombres = "Nombre Buscable"
        await session.commit()

    create_response = await client.post(
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/evento-contactos",
        headers=headers,
        json={"ids_contacto": [contacto.id_contacto, otro.id_contacto]},
    )
    assert create_response.status_code == 201

    response = await client.get(
        "/api/v1/participantes/evento-contactos",
        headers=headers,
        params={
            "id_programacion_evento": programacion.id_programacion_evento,
            "id_empresa": empresa.id_empresa,
            "search": "Buscable",
            "page": 1,
            "page_size": 1,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["pages"] == 1
    assert body["items"][0]["id_contacto"] == otro.id_contacto
    assert body["items"][0]["nombre_empresa"] == empresa.nombre_empresa


async def test_obtiene_evento_contacto_por_id_y_404(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers, programacion, _, contacto, _ = await evento_contacto_context(
            session, client
        )

    created = await client.post(
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/evento-contactos",
        headers=headers,
        json={"ids_contacto": [contacto.id_contacto]},
    )
    evento_contacto = created.json()["evento_contactos"][0]

    response = await client.get(
        f"/api/v1/participantes/evento-contactos/"
        f"{evento_contacto['id_evento_contacto']}",
        headers=headers,
    )
    missing = await client.get(
        "/api/v1/participantes/evento-contactos/999999", headers=headers
    )

    assert response.status_code == 200
    assert response.json() == evento_contacto
    assert missing.status_code == 404
