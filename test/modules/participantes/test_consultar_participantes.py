import pytest

from test.modules.contactos.conftest import create_contacto
from test.modules.participantes.conftest import participante_context


pytestmark = pytest.mark.asyncio


async def test_lista_empresas_afiliadas_con_contexto(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers, evento, empresa, _, afiliacion = await participante_context(
            session, client
        )

    response = await client.get(
        f"/api/v1/participantes/eventos/{evento.id_evento}/empresas",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json() == [afiliacion]
    assert response.json()[0]["nombre_empresa"] == empresa.nombre_empresa


async def test_lista_filtra_busca_y_pagina_participantes(client, session_factory) -> None:
    async with session_factory() as session:
        actor, headers, evento, empresa, contacto, afiliacion = await participante_context(
            session, client
        )
        otro = await create_contacto(
            session, empresa=empresa, actor=actor, sequence=70_001
        )
        otro.nombres = "Nombre Buscable"
        await session.commit()

    create_response = await client.post(
        f"/api/v1/participantes/eventos/{evento.id_evento}",
        headers=headers,
        json={
            "id_evento_empresa": afiliacion["id_evento_empresa"],
            "ids_contacto": [contacto.id_contacto, otro.id_contacto],
        },
    )
    assert create_response.status_code == 201

    response = await client.get(
        "/api/v1/participantes",
        headers=headers,
        params={
            "id_evento": evento.id_evento,
            "id_empresa": empresa.id_empresa,
            "confirmacion": "SIN_RESPUESTA",
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
    assert body["items"][0]["nombre_evento"] == evento.nombre_evento
    assert body["items"][0]["nombre_empresa"] == empresa.nombre_empresa


async def test_obtiene_participante_por_id_y_404(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers, evento, _, contacto, afiliacion = await participante_context(
            session, client
        )

    created = await client.post(
        f"/api/v1/participantes/eventos/{evento.id_evento}",
        headers=headers,
        json={
            "id_evento_empresa": afiliacion["id_evento_empresa"],
            "ids_contacto": [contacto.id_contacto],
        },
    )
    participante = created.json()["participantes"][0]

    response = await client.get(
        f"/api/v1/participantes/{participante['id_participante']}",
        headers=headers,
    )
    missing = await client.get("/api/v1/participantes/999999", headers=headers)

    assert response.status_code == 200
    assert response.json() == participante
    assert missing.status_code == 404
