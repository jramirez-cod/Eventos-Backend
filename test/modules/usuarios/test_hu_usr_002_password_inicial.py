import pytest
from sqlalchemy import select

from app.core import security
from app.modules.auditoria.models import Auditoria
from app.modules.usuarios.models import Usuario
from test.modules.usuarios.conftest import (
    NEW_PASSWORD,
    access_token,
    create_initial_password_challenge,
    create_role,
    create_user,
)


pytestmark = pytest.mark.asyncio


async def test_cambio_password_inicial_correcto_actualiza_estado_y_audita(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        rol = await create_role(session, "Operador")
        usuario = await create_user(
            session,
            rol,
            username="temporal",
            debe_cambiar_password=True,
        )
        await session.commit()
        user_id = usuario.id_usuario
        token, code = await create_initial_password_challenge(session, usuario)
        await session.commit()

    response = await client.post(
        "/api/v1/auth/cambiar-password-inicial",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "codigo_verificacion": code,
            "nueva_password": NEW_PASSWORD,
            "confirmar_password": NEW_PASSWORD,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "access"
    assert body["access_token"]

    async with session_factory() as session:
        stored = await session.get(Usuario, user_id)
        assert stored.debe_cambiar_password is False
        assert security.verify_password(NEW_PASSWORD, stored.password_hash)
        audits = (
            await session.scalars(
                select(Auditoria).where(
                    Auditoria.accion == "CAMBIO_PASSWORD_INICIAL"
                )
            )
        ).all()
        assert len(audits) == 1
        audit_payload = str(audits[0].valor_nuevo).lower()
        assert "password_hash" not in audit_payload
        assert NEW_PASSWORD.lower() not in audit_payload


async def test_token_invalido_para_cambio_password_inicial(client) -> None:
    response = await client.post(
        "/api/v1/auth/cambiar-password-inicial",
        headers={"Authorization": "Bearer token-invalido"},
        json={
            "codigo_verificacion": "482913",
            "nueva_password": NEW_PASSWORD,
            "confirmar_password": NEW_PASSWORD,
        },
    )

    assert response.status_code == 401


async def test_access_token_no_puede_usarse_como_password_change(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        rol = await create_role(session, "Operador")
        usuario = await create_user(
            session,
            rol,
            username="temporal",
            debe_cambiar_password=True,
        )
        await session.commit()
        token = access_token(usuario)

    response = await client.post(
        "/api/v1/auth/cambiar-password-inicial",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "codigo_verificacion": "482913",
            "nueva_password": NEW_PASSWORD,
            "confirmar_password": NEW_PASSWORD,
        },
    )

    assert response.status_code == 401


async def test_passwords_distintas_en_cambio_inicial(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        rol = await create_role(session, "Operador")
        usuario = await create_user(session, rol, username="temporal")
        await session.commit()
        token, code = await create_initial_password_challenge(session, usuario)
        await session.commit()

    response = await client.post(
        "/api/v1/auth/cambiar-password-inicial",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "codigo_verificacion": code,
            "nueva_password": NEW_PASSWORD,
            "confirmar_password": "OtraPass1!",
        },
    )

    assert response.status_code == 400


async def test_password_no_cumple_politica_en_cambio_inicial(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        rol = await create_role(session, "Operador")
        usuario = await create_user(session, rol, username="temporal")
        await session.commit()
        token, code = await create_initial_password_challenge(session, usuario)
        await session.commit()

    response = await client.post(
        "/api/v1/auth/cambiar-password-inicial",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "codigo_verificacion": code,
            "nueva_password": "corta",
            "confirmar_password": "corta",
        },
    )

    assert response.status_code == 400


async def test_usuario_inactivo_no_puede_cambiar_password_inicial(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        rol = await create_role(session, "Operador")
        usuario = await create_user(
            session,
            rol,
            username="temporal",
            estado=False,
            debe_cambiar_password=True,
        )
        await session.commit()
        token, code = await create_initial_password_challenge(session, usuario)
        await session.commit()

    response = await client.post(
        "/api/v1/auth/cambiar-password-inicial",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "codigo_verificacion": code,
            "nueva_password": NEW_PASSWORD,
            "confirmar_password": NEW_PASSWORD,
        },
    )

    assert response.status_code == 401
