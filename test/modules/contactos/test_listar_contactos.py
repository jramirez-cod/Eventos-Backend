import pytest

from test.modules.contactos.conftest import (
    create_cargo,
    create_contacto,
    create_empresa,
    seed_contact_actor,
)


pytestmark = pytest.mark.asyncio


async def _seed_listado(session):
    actor, headers = await seed_contact_actor(session)
    empresa_a = await create_empresa(session, sequence=30)
    empresa_b = await create_empresa(session, sequence=31)
    cargo = await create_cargo(session, name="Jefe de Operaciones")
    contacto_a = await create_contacto(
        session,
        empresa=empresa_a,
        actor=actor,
        cargo=cargo,
        sequence=30,
        estado=True,
    )
    contacto_b = await create_contacto(
        session,
        empresa=empresa_b,
        actor=actor,
        cargo=cargo,
        sequence=31,
        estado=False,
    )
    await session.commit()
    return headers, empresa_a, empresa_b, contacto_a, contacto_b


async def test_buscar_contacto_por_documento(client, session_factory) -> None:
    async with session_factory() as session:
        headers, _, _, contacto, _ = await _seed_listado(session)
        documento = contacto.numero_documento

    response = await client.get(
        "/api/v1/contactos",
        headers=headers,
        params={"search": documento},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["numero_documento"] == documento


async def test_filtrar_contactos_por_empresa(client, session_factory) -> None:
    async with session_factory() as session:
        headers, empresa, _, contacto, _ = await _seed_listado(session)
        id_empresa = empresa.id_empresa
        id_contacto = contacto.id_contacto

    response = await client.get(
        "/api/v1/contactos",
        headers=headers,
        params={"id_empresa": id_empresa},
    )

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id_contacto"] == id_contacto


async def test_filtrar_contactos_por_estado(client, session_factory) -> None:
    async with session_factory() as session:
        headers, _, _, _, inactive = await _seed_listado(session)
        id_inactive = inactive.id_contacto

    response = await client.get(
        "/api/v1/contactos",
        headers=headers,
        params={"estado": "false"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id_contacto"] == id_inactive


async def test_listado_es_paginado(client, session_factory) -> None:
    async with session_factory() as session:
        headers, _, _, _, _ = await _seed_listado(session)

    response = await client.get(
        "/api/v1/contactos",
        headers=headers,
        params={"page": 2, "page_size": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["page"] == 2
    assert body["page_size"] == 1
    assert body["pages"] == 2
    assert len(body["items"]) == 1


async def test_exportar_contactos_csv(client, session_factory) -> None:
    async with session_factory() as session:
        headers, _, _, _, _ = await _seed_listado(session)

    response = await client.get("/api/v1/contactos/exportar", headers=headers)

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "id_contacto,empresa,cargo" in response.text
    assert "Empresa Contactos 30" in response.text
