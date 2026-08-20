import pytest
from sqlalchemy import select

from app.modules.auditoria.models import Auditoria
from app.modules.contactos.models import Contacto, ContactoHistorialEmpresa
from test.modules.contactos.conftest import (
    contacto_payload,
    create_cargo,
    create_empresa,
    seed_contact_actor,
)
from test.modules.usuarios.conftest import auth_header, create_role, create_user


pytestmark = pytest.mark.asyncio


async def test_crear_contacto_normaliza_celular_y_audita(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_contact_actor(session)
        empresa = await create_empresa(session, sequence=1)
        cargo = await create_cargo(session)
        await session.commit()
        payload = contacto_payload(empresa=empresa, actor=actor, cargo=cargo)

    response = await client.post(
        "/api/v1/contactos", headers=headers, json=payload
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id_contacto"] > 0
    assert body["nombre_completo"] == "Perez Ramos Juan Carlos"
    assert body["nombre_empresa"] == "Empresa Contactos 1"
    assert body["nombre_cargo"] == "Gerente General"
    assert body["celular"] == "987654321"
    assert body["estado"] is True

    async with session_factory() as session:
        contacto = await session.get(Contacto, body["id_contacto"])
        historiales = list(
            (
                await session.scalars(
                    select(ContactoHistorialEmpresa).where(
                        ContactoHistorialEmpresa.id_contacto
                        == body["id_contacto"]
                    )
                )
            ).all()
        )
        auditoria = await session.scalar(
            select(Auditoria).where(Auditoria.accion == "CREAR_CONTACTO")
        )

    assert contacto is not None
    assert contacto.celular == "987654321"
    assert len(historiales) == 1
    assert historiales[0].fecha_fin is None
    assert auditoria is not None
    assert auditoria.id_usuario == actor.id_usuario


async def test_crear_contacto_sin_autenticacion_recibe_401(client) -> None:
    response = await client.post(
        "/api/v1/contactos",
        json={
            "id_empresa": 1,
            "nombres": "Juan",
            "apellidos": "Perez",
            "genero": "M",
        },
    )
    assert response.status_code == 401


async def test_crear_contacto_sin_permiso_recibe_403(
    client, session_factory
) -> None:
    async with session_factory() as session:
        role = await create_role(session, "Rol sin permiso contactos")
        actor = await create_user(
            session, role, username="sin.permiso.contactos"
        )
        empresa = await create_empresa(session, sequence=7)
        await session.commit()
        headers = auth_header(actor)
        payload = contacto_payload(empresa=empresa, actor=actor)

    response = await client.post(
        "/api/v1/contactos", headers=headers, json=payload
    )
    assert response.status_code == 403


async def test_crear_contacto_empresa_inexistente_recibe_404(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_contact_actor(session)

    response = await client.post(
        "/api/v1/contactos",
        headers=headers,
        json={
            "id_empresa": 999_999,
            "id_tipo_documento": actor.id_tipo_documento,
            "numero_documento": "76543210",
            "nombres": "Juan",
            "apellidos": "Perez",
            "genero": "M",
        },
    )
    assert response.status_code == 404


async def test_crear_contacto_empresa_inactiva_recibe_400(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_contact_actor(session)
        empresa = await create_empresa(session, sequence=2, estado=False)
        await session.commit()
        payload = contacto_payload(empresa=empresa, actor=actor)

    response = await client.post(
        "/api/v1/contactos", headers=headers, json=payload
    )
    assert response.status_code == 400


async def test_crear_contacto_documento_duplicado_recibe_409(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_contact_actor(session)
        empresa = await create_empresa(session, sequence=3)
        await session.commit()
        payload = contacto_payload(empresa=empresa, actor=actor)

    first = await client.post("/api/v1/contactos", headers=headers, json=payload)
    second = await client.post(
        "/api/v1/contactos",
        headers=headers,
        json={**payload, "correo": "otro@example.com"},
    )

    assert first.status_code == 201
    assert second.status_code == 409


async def test_crear_contacto_cargo_inexistente_recibe_404(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_contact_actor(session)
        empresa = await create_empresa(session, sequence=4)
        await session.commit()
        payload = contacto_payload(empresa=empresa, actor=actor)
        payload["id_cargo"] = 999_999

    response = await client.post(
        "/api/v1/contactos", headers=headers, json=payload
    )
    assert response.status_code == 404


async def test_crear_contacto_cargo_inactivo_recibe_400(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_contact_actor(session)
        empresa = await create_empresa(session, sequence=5)
        cargo = await create_cargo(session, estado=False)
        await session.commit()
        payload = contacto_payload(empresa=empresa, actor=actor, cargo=cargo)

    response = await client.post(
        "/api/v1/contactos", headers=headers, json=payload
    )
    assert response.status_code == 400


async def test_crear_contacto_celular_invalido_recibe_400(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_contact_actor(session)
        empresa = await create_empresa(session, sequence=6)
        await session.commit()
        payload = contacto_payload(empresa=empresa, actor=actor)
        payload["celular"] = "1234"

    response = await client.post(
        "/api/v1/contactos", headers=headers, json=payload
    )
    assert response.status_code == 400
