from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core import security
from app.modules.auditoria.models import Auditoria
from app.modules.usuarios.models import Usuario, UsuarioTokenRecuperacion
from test.modules.usuarios.conftest import (
    NEW_PASSWORD,
    VALID_PASSWORD,
    create_recovery_token,
    create_role,
    create_user,
)


pytestmark = pytest.mark.asyncio


async def test_solicitud_recuperacion_correo_existente_crea_token_hash(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        rol = await create_role(session, "Operador")
        await create_user(session, rol, username="jperez", email="jperez@codip.pe")
        await session.commit()

    response = await client.post(
        "/api/v1/auth/recuperar-password",
        json={"correo": "jperez@codip.pe"},
    )

    assert response.status_code == 200
    async with session_factory() as session:
        tokens = (await session.scalars(select(UsuarioTokenRecuperacion))).all()
        assert len(tokens) == 1
        assert tokens[0].token_hash
        assert "recovery" not in tokens[0].token_hash


async def test_solicitud_recuperacion_correo_inexistente_devuelve_misma_respuesta(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        rol = await create_role(session, "Operador")
        await create_user(session, rol, username="jperez", email="jperez@codip.pe")
        await session.commit()

    existing = await client.post(
        "/api/v1/auth/recuperar-password",
        json={"correo": "jperez@codip.pe"},
    )
    missing = await client.post(
        "/api/v1/auth/recuperar-password",
        json={"correo": "nadie@codip.pe"},
    )

    assert existing.status_code == 200
    assert missing.status_code == 200
    assert existing.json() == missing.json()


async def test_restablecer_password_token_valido_actualiza_y_audita(
    client,
    session_factory,
) -> None:
    token = "token-recuperacion-valido"
    async with session_factory() as session:
        rol = await create_role(session, "Operador")
        usuario = await create_user(
            session,
            rol,
            username="jperez",
            password=VALID_PASSWORD,
            debe_cambiar_password=True,
        )
        await create_recovery_token(session, usuario, token=token)
        await session.commit()
        user_id = usuario.id_usuario

    response = await client.post(
        "/api/v1/auth/restablecer-password",
        json={
            "token": token,
            "nueva_password": NEW_PASSWORD,
            "confirmar_password": NEW_PASSWORD,
        },
    )

    assert response.status_code == 200
    assert response.json()["access_token"]

    async with session_factory() as session:
        stored = await session.get(Usuario, user_id)
        assert security.verify_password(NEW_PASSWORD, stored.password_hash)
        assert stored.debe_cambiar_password is False
        stored_token = await session.scalar(
            select(UsuarioTokenRecuperacion).where(
                UsuarioTokenRecuperacion.token_hash
                == security.hash_recovery_token(token)
            )
        )
        assert stored_token.utilizado_en is not None
        audits = (
            await session.scalars(
                select(Auditoria).where(
                    Auditoria.accion == "RESTABLECIMIENTO_PASSWORD"
                )
            )
        ).all()
        assert len(audits) == 1
        assert "token" not in str(audits[0].valor_nuevo).lower()


@pytest.mark.parametrize(
    ("token", "expira_en", "utilizado_en", "expected_token"),
    [
        (
            "expirado",
            datetime.now(UTC) - timedelta(minutes=1),
            None,
            "expirado",
        ),
        (
            "usado",
            datetime.now(UTC) + timedelta(minutes=30),
            datetime.now(UTC),
            "usado",
        ),
    ],
)
async def test_restablecer_password_rechaza_token_expirado_o_usado(
    client,
    session_factory,
    token,
    expira_en,
    utilizado_en,
    expected_token,
) -> None:
    async with session_factory() as session:
        rol = await create_role(session, "Operador")
        usuario = await create_user(session, rol, username=f"user-{token}")
        await create_recovery_token(
            session,
            usuario,
            token=token,
            expira_en=expira_en,
            utilizado_en=utilizado_en,
        )
        await session.commit()

    response = await client.post(
        "/api/v1/auth/restablecer-password",
        json={
            "token": expected_token,
            "nueva_password": NEW_PASSWORD,
            "confirmar_password": NEW_PASSWORD,
        },
    )

    assert response.status_code == 401


async def test_restablecer_password_token_invalido(client) -> None:
    response = await client.post(
        "/api/v1/auth/restablecer-password",
        json={
            "token": "token-que-no-existe",
            "nueva_password": NEW_PASSWORD,
            "confirmar_password": NEW_PASSWORD,
        },
    )

    assert response.status_code == 401


async def test_restablecer_password_no_reutiliza_token(
    client,
    session_factory,
) -> None:
    token = "token-un-solo-uso"
    async with session_factory() as session:
        rol = await create_role(session, "Operador")
        usuario = await create_user(session, rol, username="jperez")
        await create_recovery_token(session, usuario, token=token)
        await session.commit()

    first = await client.post(
        "/api/v1/auth/restablecer-password",
        json={
            "token": token,
            "nueva_password": NEW_PASSWORD,
            "confirmar_password": NEW_PASSWORD,
        },
    )
    second = await client.post(
        "/api/v1/auth/restablecer-password",
        json={
            "token": token,
            "nueva_password": "OtraNueva1!",
            "confirmar_password": "OtraNueva1!",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 401


async def test_restablecer_password_valida_confirmacion_y_politica(
    client,
    session_factory,
) -> None:
    token = "token-policy"
    async with session_factory() as session:
        rol = await create_role(session, "Operador")
        usuario = await create_user(session, rol, username="jperez")
        await create_recovery_token(session, usuario, token=token)
        await session.commit()

    mismatch = await client.post(
        "/api/v1/auth/restablecer-password",
        json={
            "token": token,
            "nueva_password": NEW_PASSWORD,
            "confirmar_password": "OtraNueva1!",
        },
    )
    weak = await client.post(
        "/api/v1/auth/restablecer-password",
        json={"token": token, "nueva_password": "corta", "confirmar_password": "corta"},
    )

    assert mismatch.status_code == 400
    assert weak.status_code == 400
