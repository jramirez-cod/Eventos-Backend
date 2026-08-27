import pytest

from test.modules.contactos.conftest import create_empresa, seed_contact_actor


pytestmark = pytest.mark.asyncio


def _contacto_payload(
    *, id_empresa: int, sequence: int, es_contacto_principal: bool
) -> dict:
    return {
        "id_empresa": id_empresa,
        "nombres": f"Nombre{sequence}",
        "apellidos": f"Apellido{sequence}",
        "genero": "M",
        "es_contacto_principal": es_contacto_principal,
    }


async def test_marcar_contacto_principal_desmarca_a_los_demas_de_la_misma_empresa(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_contact_actor(session)
        empresa = await create_empresa(session, sequence=91_001)
        await session.commit()
        id_empresa = empresa.id_empresa

    primero = await client.post(
        "/api/v1/contactos",
        headers=headers,
        json=_contacto_payload(id_empresa=id_empresa, sequence=1, es_contacto_principal=True),
    )
    assert primero.status_code == 201, primero.text
    assert primero.json()["es_contacto_principal"] is True

    segundo = await client.post(
        "/api/v1/contactos",
        headers=headers,
        json=_contacto_payload(id_empresa=id_empresa, sequence=2, es_contacto_principal=True),
    )
    assert segundo.status_code == 201, segundo.text
    assert segundo.json()["es_contacto_principal"] is True

    releido = await client.get(
        f"/api/v1/contactos/{primero.json()['id_contacto']}", headers=headers
    )
    assert releido.status_code == 200
    assert releido.json()["es_contacto_principal"] is False


async def test_actualizar_contacto_a_principal_desmarca_a_los_demas(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_contact_actor(session)
        empresa = await create_empresa(session, sequence=91_002)
        await session.commit()
        id_empresa = empresa.id_empresa

    primero = await client.post(
        "/api/v1/contactos",
        headers=headers,
        json=_contacto_payload(id_empresa=id_empresa, sequence=3, es_contacto_principal=True),
    )
    assert primero.status_code == 201, primero.text

    segundo = await client.post(
        "/api/v1/contactos",
        headers=headers,
        json=_contacto_payload(id_empresa=id_empresa, sequence=4, es_contacto_principal=False),
    )
    assert segundo.status_code == 201, segundo.text

    actualizado = await client.patch(
        f"/api/v1/contactos/{segundo.json()['id_contacto']}",
        headers=headers,
        json={"es_contacto_principal": True},
    )
    assert actualizado.status_code == 200, actualizado.text
    assert actualizado.json()["es_contacto_principal"] is True

    releido = await client.get(
        f"/api/v1/contactos/{primero.json()['id_contacto']}", headers=headers
    )
    assert releido.status_code == 200
    assert releido.json()["es_contacto_principal"] is False
