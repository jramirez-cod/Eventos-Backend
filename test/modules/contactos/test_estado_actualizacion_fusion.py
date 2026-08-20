import pytest
from sqlalchemy import select

from app.modules.auditoria.models import Auditoria
from app.modules.contactos.models import Contacto, ContactoHistorialEmpresa
from test.modules.contactos.conftest import (
    create_cargo,
    create_contacto,
    create_empresa,
    seed_contact_actor,
)


pytestmark = pytest.mark.asyncio


async def test_inactivar_y_reactivar_contacto_sin_eliminarlo(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_contact_actor(session)
        empresa = await create_empresa(session, sequence=20)
        contacto = await create_contacto(
            session, empresa=empresa, actor=actor, sequence=20
        )
        await session.commit()
        id_contacto = contacto.id_contacto

    inactive = await client.patch(
        f"/api/v1/contactos/{id_contacto}/estado",
        headers=headers,
        json={"estado": False, "motivo": "Baja administrativa"},
    )
    active = await client.patch(
        f"/api/v1/contactos/{id_contacto}/estado",
        headers=headers,
        json={"estado": True},
    )

    assert inactive.status_code == 200
    assert inactive.json()["estado"] is False
    assert active.status_code == 200
    assert active.json()["estado"] is True

    async with session_factory() as session:
        stored = await session.get(Contacto, id_contacto)
        actions = set(
            (
                await session.scalars(
                    select(Auditoria.accion).where(
                        Auditoria.entidad == "contacto",
                        Auditoria.id_entidad == str(id_contacto),
                    )
                )
            ).all()
        )
    assert stored is not None
    assert stored.estado is True
    assert {"INACTIVAR_CONTACTO", "REACTIVAR_CONTACTO"} <= actions


async def test_cambiar_estado_contacto_inexistente_recibe_404(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_contact_actor(session)

    response = await client.patch(
        "/api/v1/contactos/999999/estado",
        headers=headers,
        json={"estado": False},
    )
    assert response.status_code == 404


async def test_actualizar_contacto_normaliza_celular_y_valida_cargo(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_contact_actor(session)
        empresa = await create_empresa(session, sequence=21)
        contacto = await create_contacto(
            session, empresa=empresa, actor=actor, sequence=21
        )
        cargo = await create_cargo(session, name="Director Comercial")
        await session.commit()
        id_contacto = contacto.id_contacto
        id_cargo = cargo.id_cargo

    response = await client.patch(
        f"/api/v1/contactos/{id_contacto}",
        headers=headers,
        json={
            "id_cargo": id_cargo,
            "celular": "+51 987 654 321",
            "nombres": "Nombre Actualizado",
        },
    )

    assert response.status_code == 200
    assert response.json()["celular"] == "+51987654321"
    assert response.json()["nombre_cargo"] == "Director Comercial"
    assert response.json()["nombres"] == "Nombre Actualizado"


async def test_fusionar_inactiva_duplicado_sin_borrarlo(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_contact_actor(session)
        empresa = await create_empresa(session, sequence=22)
        principal = await create_contacto(
            session, empresa=empresa, actor=actor, sequence=22
        )
        duplicado = await create_contacto(
            session, empresa=empresa, actor=actor, sequence=23
        )
        await session.commit()
        id_principal = principal.id_contacto
        id_duplicado = duplicado.id_contacto

    response = await client.post(
        "/api/v1/contactos/fusionar",
        headers=headers,
        json={
            "id_contacto_principal": id_principal,
            "id_contacto_duplicado": id_duplicado,
            "motivo": "Duplicidad detectada",
        },
    )

    assert response.status_code == 200
    assert response.json()["id_contacto"] == id_principal

    async with session_factory() as session:
        stored_principal = await session.get(Contacto, id_principal)
        stored_duplicate = await session.get(Contacto, id_duplicado)
        current_duplicate_history = await session.scalar(
            select(ContactoHistorialEmpresa).where(
                ContactoHistorialEmpresa.id_contacto == id_duplicado,
                ContactoHistorialEmpresa.fecha_fin.is_(None),
            )
        )
        audit = await session.scalar(
            select(Auditoria).where(Auditoria.accion == "FUSIONAR_CONTACTO")
        )

    assert stored_principal is not None
    assert stored_principal.estado is True
    assert stored_duplicate is not None
    assert stored_duplicate.estado is False
    assert current_duplicate_history is None
    assert audit is not None


async def test_fusionar_mismo_contacto_recibe_400(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_contact_actor(session)

    response = await client.post(
        "/api/v1/contactos/fusionar",
        headers=headers,
        json={
            "id_contacto_principal": 1,
            "id_contacto_duplicado": 1,
            "motivo": "Duplicidad detectada",
        },
    )
    assert response.status_code == 400
