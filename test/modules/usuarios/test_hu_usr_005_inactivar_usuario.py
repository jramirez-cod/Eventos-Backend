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


async def test_usuario_autorizado_puede_inactivar(client, session_factory) -> None:
    async with session_factory() as session:
        _, admin = await seed_admin_with_permissions(session)
        role = await create_role(session, "Operador")
        target = await create_user(session, role, username="ainactivar")
        await session.commit()
        target_id = target.id_usuario
        headers = auth_header(admin)

    response = await client.patch(
        f"/api/v1/usuarios/{target_id}/inactivar",
        headers=headers,
        json={"motivo": "Baja administrativa"},
    )

    assert response.status_code == 200
    assert response.json()["estado"] is False

    async with session_factory() as session:
        stored = await session.get(Usuario, target_id)
        assert stored is not None
        assert stored.estado is False


async def test_inactivar_sin_permiso_recibe_403(client, session_factory) -> None:
    async with session_factory() as session:
        role = await create_role(session, "Operador")
        actor = await create_user(session, role, username="sinpermiso")
        target = await create_user(session, role, username="target")
        await session.commit()
        headers = auth_header(actor)
        target_id = target.id_usuario

    response = await client.patch(
        f"/api/v1/usuarios/{target_id}/inactivar",
        headers=headers,
        json={},
    )

    assert response.status_code == 403


async def test_inactivar_usuario_inexistente_recibe_404(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        _, admin = await seed_admin_with_permissions(session)
        await session.commit()
        headers = auth_header(admin)

    response = await client.patch(
        "/api/v1/usuarios/9999/inactivar",
        headers=headers,
        json={},
    )

    assert response.status_code == 404


async def test_inactivar_genera_auditoria(client, session_factory) -> None:
    async with session_factory() as session:
        _, admin = await seed_admin_with_permissions(session)
        role = await create_role(session, "Operador")
        target = await create_user(session, role, username="auditable")
        await session.commit()
        headers = auth_header(admin)
        target_id = target.id_usuario
        actor_id = admin.id_usuario

    response = await client.patch(
        f"/api/v1/usuarios/{target_id}/inactivar",
        headers=headers,
        json={"motivo": "Control interno"},
    )

    assert response.status_code == 200
    async with session_factory() as session:
        audits = (
            await session.scalars(
                select(Auditoria).where(Auditoria.accion == "INACTIVACION_USUARIO")
            )
        ).all()
        assert len(audits) == 1
        assert audits[0].id_usuario == actor_id
        assert audits[0].id_entidad == str(target_id)
        assert audits[0].valor_anterior == {"estado": True}
        assert audits[0].valor_nuevo == {"estado": False}
        assert audits[0].motivo == "Control interno"


async def test_jwt_anterior_deja_de_funcionar_despues_de_inactivacion(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        _, admin = await seed_admin_with_permissions(session)
        role = await create_role(session, "Operador")
        target = await create_user(session, role, username="tokenviejo")
        await session.commit()
        old_headers = auth_header(target)
        admin_headers = auth_header(admin)
        target_id = target.id_usuario
        role_id = role.id_rol

    inactivate = await client.patch(
        f"/api/v1/usuarios/{target_id}/inactivar",
        headers=admin_headers,
        json={},
    )
    assert inactivate.status_code == 200

    response = await client.post(
        "/api/v1/usuarios",
        headers=old_headers,
        json={
            "id_rol": role_id,
            "nombre_usuario": "intento",
            "nombres": "Intento",
            "apellidos": "Fallido",
            "correo": "intento@codip.pe",
            "password_temporal": "74859632",
        },
    )

    assert response.status_code == 401
