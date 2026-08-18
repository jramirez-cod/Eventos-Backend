from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core import security
from app.modules.auditoria.models import Auditoria
from app.modules.usuarios.models import Usuario, UsuarioTokenRecuperacion
from test.modules.usuarios.conftest import (
    NEW_PASSWORD,
    VALID_PASSWORD,
    create_role,
    create_user,
)


pytestmark = pytest.mark.asyncio

CODIGO_VERIFICACION = "482913"


def _patch_codigo(monkeypatch: pytest.MonkeyPatch, codigo: str = CODIGO_VERIFICACION) -> None:
    monkeypatch.setattr(security, "generate_initial_verification_code", lambda: codigo)


async def test_solicitud_recuperacion_correo_existente_crea_codigo_hash(
    client,
    session_factory,
    monkeypatch,
) -> None:
    _patch_codigo(monkeypatch)
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
        assert CODIGO_VERIFICACION not in tokens[0].token_hash


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


async def test_restablecer_password_codigo_valido_actualiza_y_audita(
    client,
    session_factory,
    monkeypatch,
) -> None:
    _patch_codigo(monkeypatch)
    async with session_factory() as session:
        rol = await create_role(session, "Operador")
        usuario = await create_user(
            session,
            rol,
            username="jperez",
            email="jperez@codip.pe",
            password=VALID_PASSWORD,
            debe_cambiar_password=True,
        )
        await session.commit()
        user_id = usuario.id_usuario

    solicitud = await client.post(
        "/api/v1/auth/recuperar-password",
        json={"correo": "jperez@codip.pe"},
    )
    assert solicitud.status_code == 200

    response = await client.post(
        "/api/v1/auth/restablecer-password",
        json={
            "correo": "jperez@codip.pe",
            "codigo_verificacion": CODIGO_VERIFICACION,
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
                == security.hash_recovery_code(
                    correo="jperez@codip.pe", code=CODIGO_VERIFICACION
                )
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
        audit_payload = str(audits[0].valor_nuevo).lower()
        assert CODIGO_VERIFICACION not in audit_payload
        assert NEW_PASSWORD.lower() not in audit_payload


@pytest.mark.parametrize(
    ("mutar_expirado", "mutar_usado"),
    [
        (True, False),
        (False, True),
    ],
)
async def test_restablecer_password_rechaza_codigo_expirado_o_usado(
    client,
    session_factory,
    monkeypatch,
    mutar_expirado,
    mutar_usado,
) -> None:
    _patch_codigo(monkeypatch)
    async with session_factory() as session:
        rol = await create_role(session, "Operador")
        await create_user(session, rol, username="jperez", email="jperez@codip.pe")
        await session.commit()

    await client.post(
        "/api/v1/auth/recuperar-password",
        json={"correo": "jperez@codip.pe"},
    )

    async with session_factory() as session:
        stored_token = await session.scalar(select(UsuarioTokenRecuperacion))
        if mutar_expirado:
            stored_token.expira_en = datetime.now(UTC) - timedelta(minutes=1)
        if mutar_usado:
            stored_token.utilizado_en = datetime.now(UTC)
        await session.commit()

    response = await client.post(
        "/api/v1/auth/restablecer-password",
        json={
            "correo": "jperez@codip.pe",
            "codigo_verificacion": CODIGO_VERIFICACION,
            "nueva_password": NEW_PASSWORD,
            "confirmar_password": NEW_PASSWORD,
        },
    )

    assert response.status_code == 401


async def test_restablecer_password_codigo_invalido(client, session_factory) -> None:
    async with session_factory() as session:
        rol = await create_role(session, "Operador")
        await create_user(session, rol, username="jperez", email="jperez@codip.pe")
        await session.commit()

    response = await client.post(
        "/api/v1/auth/restablecer-password",
        json={
            "correo": "jperez@codip.pe",
            "codigo_verificacion": "000000",
            "nueva_password": NEW_PASSWORD,
            "confirmar_password": NEW_PASSWORD,
        },
    )

    assert response.status_code == 401


async def test_restablecer_password_correo_inexistente_recibe_401(client) -> None:
    response = await client.post(
        "/api/v1/auth/restablecer-password",
        json={
            "correo": "nadie@codip.pe",
            "codigo_verificacion": "000000",
            "nueva_password": NEW_PASSWORD,
            "confirmar_password": NEW_PASSWORD,
        },
    )

    assert response.status_code == 401


async def test_restablecer_password_no_reutiliza_codigo(
    client,
    session_factory,
    monkeypatch,
) -> None:
    _patch_codigo(monkeypatch)
    async with session_factory() as session:
        rol = await create_role(session, "Operador")
        await create_user(session, rol, username="jperez", email="jperez@codip.pe")
        await session.commit()

    await client.post(
        "/api/v1/auth/recuperar-password",
        json={"correo": "jperez@codip.pe"},
    )

    payload = {
        "correo": "jperez@codip.pe",
        "codigo_verificacion": CODIGO_VERIFICACION,
        "nueva_password": NEW_PASSWORD,
        "confirmar_password": NEW_PASSWORD,
    }
    first = await client.post("/api/v1/auth/restablecer-password", json=payload)
    second = await client.post(
        "/api/v1/auth/restablecer-password",
        json={**payload, "nueva_password": "OtraNueva1!", "confirmar_password": "OtraNueva1!"},
    )

    assert first.status_code == 200
    assert second.status_code == 401


async def test_restablecer_password_valida_confirmacion_y_politica(
    client,
    session_factory,
    monkeypatch,
) -> None:
    _patch_codigo(monkeypatch)
    async with session_factory() as session:
        rol = await create_role(session, "Operador")
        await create_user(session, rol, username="jperez", email="jperez@codip.pe")
        await session.commit()

    await client.post(
        "/api/v1/auth/recuperar-password",
        json={"correo": "jperez@codip.pe"},
    )

    mismatch = await client.post(
        "/api/v1/auth/restablecer-password",
        json={
            "correo": "jperez@codip.pe",
            "codigo_verificacion": CODIGO_VERIFICACION,
            "nueva_password": NEW_PASSWORD,
            "confirmar_password": "OtraNueva1!",
        },
    )
    weak = await client.post(
        "/api/v1/auth/restablecer-password",
        json={
            "correo": "jperez@codip.pe",
            "codigo_verificacion": CODIGO_VERIFICACION,
            "nueva_password": "corta",
            "confirmar_password": "corta",
        },
    )

    assert mismatch.status_code == 400
    assert weak.status_code == 400
