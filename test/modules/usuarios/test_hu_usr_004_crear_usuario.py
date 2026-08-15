import pytest
from sqlalchemy import select

from app.core import security
from app.modules.auditoria.models import Auditoria
from app.modules.usuarios.models import Usuario
from test.modules.usuarios.conftest import (
    auth_header,
    create_role,
    create_user,
    seed_admin_with_permissions,
)


pytestmark = pytest.mark.asyncio


def usuario_payload(id_rol: int) -> dict[str, object]:
    return {
        "id_rol": id_rol,
        "nombre_usuario": "mlopez",
        "nombres": "Maria",
        "apellidos": "Lopez",
        "correo": "mlopez@codip.pe",
        "password_temporal": "Temporal1!",
    }


async def test_administrador_con_permiso_puede_crear_usuario(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        _, admin = await seed_admin_with_permissions(session)
        user_role = await create_role(session, "Operador")
        await session.commit()
        role_id = user_role.id_rol
        headers = auth_header(admin)

    response = await client.post(
        "/api/v1/usuarios",
        headers=headers,
        json=usuario_payload(role_id),
    )

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id_usuario": body["id_usuario"],
        "nombre_usuario": "mlopez",
        "nombres": "Maria",
        "apellidos": "Lopez",
        "correo": "mlopez@codip.pe",
        "id_rol": role_id,
        "nombre_rol": "Operador",
        "estado": True,
        "debe_cambiar_password": True,
    }
    assert "password" not in body

    async with session_factory() as session:
        created = await session.scalar(
            select(Usuario).where(Usuario.nombre_usuario == "mlopez")
        )
        assert created is not None
        assert created.debe_cambiar_password is True
        assert created.password_hash != "Temporal1!"
        assert security.verify_password("Temporal1!", created.password_hash)
        audits = (
            await session.scalars(
                select(Auditoria).where(Auditoria.accion == "CREACION_USUARIO")
            )
        ).all()
        assert len(audits) == 1
        audit_payload = str(audits[0].valor_nuevo).lower()
        assert "password_hash" not in audit_payload
        assert "temporal1!" not in audit_payload


async def test_usuario_sin_permiso_recibe_403(client, session_factory) -> None:
    async with session_factory() as session:
        role = await create_role(session, "Operador")
        actor = await create_user(session, role, username="operador")
        target_role = await create_role(session, "Invitado")
        await session.commit()
        headers = auth_header(actor)
        role_id = target_role.id_rol

    response = await client.post(
        "/api/v1/usuarios",
        headers=headers,
        json=usuario_payload(role_id),
    )

    assert response.status_code == 403


async def test_username_duplicado_recibe_409(client, session_factory) -> None:
    async with session_factory() as session:
        _, admin = await seed_admin_with_permissions(session)
        role = await create_role(session, "Operador")
        await create_user(session, role, username="mlopez", email="otro@codip.pe")
        await session.commit()
        headers = auth_header(admin)

    response = await client.post(
        "/api/v1/usuarios",
        headers=headers,
        json=usuario_payload(role.id_rol),
    )

    assert response.status_code == 409


async def test_correo_duplicado_recibe_409(client, session_factory) -> None:
    async with session_factory() as session:
        _, admin = await seed_admin_with_permissions(session)
        role = await create_role(session, "Operador")
        await create_user(session, role, username="otro", email="mlopez@codip.pe")
        await session.commit()
        headers = auth_header(admin)

    payload = usuario_payload(role.id_rol)
    payload["nombre_usuario"] = "distinto"
    response = await client.post("/api/v1/usuarios", headers=headers, json=payload)

    assert response.status_code == 409


async def test_rol_inexistente_recibe_404(client, session_factory) -> None:
    async with session_factory() as session:
        _, admin = await seed_admin_with_permissions(session)
        await session.commit()
        headers = auth_header(admin)

    response = await client.post(
        "/api/v1/usuarios",
        headers=headers,
        json=usuario_payload(9999),
    )

    assert response.status_code == 404


async def test_password_temporal_debe_cumplir_politica(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        _, admin = await seed_admin_with_permissions(session)
        role = await create_role(session, "Operador")
        await session.commit()
        headers = auth_header(admin)

    payload = usuario_payload(role.id_rol)
    payload["password_temporal"] = "corta"
    response = await client.post("/api/v1/usuarios", headers=headers, json=payload)

    assert response.status_code == 400
