import pytest
from sqlalchemy import select

from app.modules.auditoria.models import Auditoria
from app.modules.usuarios.models import Usuario
from test.modules.usuarios.conftest import (
    auth_header,
    create_role,
    create_user,
    seed_admin_with_permissions,
)


pytestmark = pytest.mark.asyncio


async def test_usuario_autorizado_puede_actualizar(client, session_factory) -> None:
    async with session_factory() as session:
        _, admin = await seed_admin_with_permissions(session)
        role = await create_role(session, "Operador")
        target = await create_user(session, role, username="aeditar", email="aeditar@codip.pe")
        await session.commit()
        target_id = target.id_usuario
        role_id = role.id_rol
        headers = auth_header(admin)

    response = await client.patch(
        f"/api/v1/usuarios/{target_id}",
        headers=headers,
        json={
            "id_rol": role_id,
            "id_tipo_documento": 1,
            "numero_documento": "74859632",
            "nombres": "Actualizado",
            "apellidos": "Correctamente",
            "correo": "actualizado@codip.pe",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["nombres"] == "Actualizado"
    assert body["apellidos"] == "Correctamente"
    assert body["correo"] == "actualizado@codip.pe"
    assert body["numero_documento"] == "74859632"

    async with session_factory() as session:
        stored = await session.get(Usuario, target_id)
        assert stored is not None
        assert stored.nombres == "Actualizado"
        assert stored.correo == "actualizado@codip.pe"


async def test_actualizar_sin_permiso_recibe_403(client, session_factory) -> None:
    async with session_factory() as session:
        role = await create_role(session, "Operador")
        actor = await create_user(session, role, username="sinpermiso2")
        target = await create_user(session, role, username="target2")
        await session.commit()
        headers = auth_header(actor)
        target_id = target.id_usuario
        role_id = role.id_rol

    response = await client.patch(
        f"/api/v1/usuarios/{target_id}",
        headers=headers,
        json={
            "id_rol": role_id,
            "id_tipo_documento": 1,
            "numero_documento": "74859633",
            "nombres": "X",
            "apellidos": "Y",
            "correo": "x@codip.pe",
        },
    )

    assert response.status_code == 403


async def test_actualizar_usuario_inexistente_recibe_404(client, session_factory) -> None:
    async with session_factory() as session:
        _, admin = await seed_admin_with_permissions(session)
        role = await create_role(session, "Operador")
        await session.commit()
        headers = auth_header(admin)
        role_id = role.id_rol

    response = await client.patch(
        "/api/v1/usuarios/9999",
        headers=headers,
        json={
            "id_rol": role_id,
            "id_tipo_documento": 1,
            "numero_documento": "74859634",
            "nombres": "X",
            "apellidos": "Y",
            "correo": "x2@codip.pe",
        },
    )

    assert response.status_code == 404


async def test_actualizar_con_correo_duplicado_recibe_409(client, session_factory) -> None:
    async with session_factory() as session:
        _, admin = await seed_admin_with_permissions(session)
        role = await create_role(session, "Operador")
        otro = await create_user(session, role, username="otro1", email="ocupado@codip.pe")
        target = await create_user(session, role, username="target3")
        await session.commit()
        headers = auth_header(admin)
        target_id = target.id_usuario
        role_id = role.id_rol

    response = await client.patch(
        f"/api/v1/usuarios/{target_id}",
        headers=headers,
        json={
            "id_rol": role_id,
            "id_tipo_documento": 1,
            "numero_documento": "74859635",
            "nombres": "X",
            "apellidos": "Y",
            "correo": "ocupado@codip.pe",
        },
    )

    assert response.status_code == 409


async def test_actualizar_conservando_su_propio_correo_no_falla(client, session_factory) -> None:
    async with session_factory() as session:
        _, admin = await seed_admin_with_permissions(session)
        role = await create_role(session, "Operador")
        target = await create_user(session, role, username="target4", email="propio@codip.pe")
        await session.commit()
        headers = auth_header(admin)
        target_id = target.id_usuario
        role_id = role.id_rol

    response = await client.patch(
        f"/api/v1/usuarios/{target_id}",
        headers=headers,
        json={
            "id_rol": role_id,
            "id_tipo_documento": 1,
            "numero_documento": "74859636",
            "nombres": "Mismo",
            "apellidos": "Correo",
            "correo": "propio@codip.pe",
        },
    )

    assert response.status_code == 200, response.text


async def test_actualizar_genera_auditoria(client, session_factory) -> None:
    async with session_factory() as session:
        _, admin = await seed_admin_with_permissions(session)
        role = await create_role(session, "Operador")
        target = await create_user(session, role, username="auditable2")
        await session.commit()
        headers = auth_header(admin)
        target_id = target.id_usuario
        role_id = role.id_rol
        actor_id = admin.id_usuario

    response = await client.patch(
        f"/api/v1/usuarios/{target_id}",
        headers=headers,
        json={
            "id_rol": role_id,
            "id_tipo_documento": 1,
            "numero_documento": "74859637",
            "nombres": "Con",
            "apellidos": "Auditoria",
            "correo": "auditoria@codip.pe",
        },
    )

    assert response.status_code == 200
    async with session_factory() as session:
        audits = (
            await session.scalars(
                select(Auditoria).where(Auditoria.accion == "ACTUALIZACION_USUARIO")
            )
        ).all()
        assert len(audits) == 1
        assert audits[0].id_usuario == actor_id
        assert audits[0].id_entidad == str(target_id)
        assert audits[0].valor_nuevo["nombres"] == "Con"


async def test_obtener_usuario_por_id(client, session_factory) -> None:
    async with session_factory() as session:
        _, admin = await seed_admin_with_permissions(session)
        role = await create_role(session, "Operador")
        target = await create_user(session, role, username="consultable")
        await session.commit()
        headers = auth_header(admin)
        target_id = target.id_usuario

    response = await client.get(f"/api/v1/usuarios/{target_id}", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["id_usuario"] == target_id


async def test_obtener_usuario_inexistente_recibe_404(client, session_factory) -> None:
    async with session_factory() as session:
        _, admin = await seed_admin_with_permissions(session)
        await session.commit()
        headers = auth_header(admin)

    response = await client.get("/api/v1/usuarios/9999", headers=headers)

    assert response.status_code == 404
