from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core import security
from app.modules.auditoria.models import Auditoria
from app.core.config import settings
from app.modules.usuarios.auth_service import (
    AuthService,
    development_initial_password_code_notifier,
)
from app.modules.usuarios.dto import LoginRequestDTO
from app.modules.usuarios.models import Usuario, UsuarioTokenRecuperacion
from test.modules.usuarios.conftest import (
    NEW_PASSWORD,
    auth_header,
    create_role,
    create_user,
    seed_admin_with_permissions,
)


pytestmark = pytest.mark.asyncio

DNI_TEMPORAL = "74859632"
CODIGO_VERIFICACION = "482913"


async def test_flujo_completo_admin_dni_codigo_password_y_login_normal(
    client,
    session_factory,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        security,
        "generate_initial_verification_code",
        lambda: CODIGO_VERIFICACION,
    )

    async with session_factory() as session:
        _, admin = await seed_admin_with_permissions(session)
        user_role = await create_role(session, "Operador")
        await session.commit()
        admin_headers = auth_header(admin)
        role_id = user_role.id_rol

    create_response = await client.post(
        "/api/v1/usuarios",
        headers=admin_headers,
        json={
            "id_rol": role_id,
            "nombre_usuario": "DylanCodip",
            "nombres": "Dylan",
            "apellidos": "Codip",
            "correo": "dylan@codip.pe",
            "password_temporal": DNI_TEMPORAL,
        },
    )

    assert create_response.status_code == 201
    user_id = create_response.json()["id_usuario"]
    assert create_response.json()["debe_cambiar_password"] is True

    async with session_factory() as session:
        created = await session.get(Usuario, user_id)
        assert created is not None
        assert created.password_hash != DNI_TEMPORAL
        assert security.verify_password(DNI_TEMPORAL, created.password_hash)

    first_login = await client.post(
        "/api/v1/auth/login",
        json={
            "nombre_usuario": "DylanCodip",
            "password": DNI_TEMPORAL,
        },
    )

    assert first_login.status_code == 200
    first_login_body = first_login.json()
    assert first_login_body["debe_cambiar_password"] is True
    assert first_login_body["token_type"] == "password_change"
    assert first_login_body["access_token"] is None
    assert first_login_body["password_change_token"]
    assert first_login_body["codigo_verificacion_requerido"] is True
    assert first_login_body["correo_enmascarado"] == "d****@codip.pe"

    password_change_token = first_login_body["password_change_token"]
    token_payload = security.decode_password_change_token(password_change_token)
    expected_code_hash = security.hash_initial_verification_code(
        token_id=str(token_payload["jti"]),
        code=CODIGO_VERIFICACION,
    )

    async with session_factory() as session:
        stored_code = await session.scalar(
            select(UsuarioTokenRecuperacion).where(
                UsuarioTokenRecuperacion.token_hash == expected_code_hash
            )
        )
        assert stored_code is not None
        assert stored_code.id_usuario == user_id
        assert stored_code.token_hash != CODIGO_VERIFICACION
        assert stored_code.utilizado_en is None

    limited_token_attempt = await client.get(
        "/api/v1/usuarios",
        headers={"Authorization": f"Bearer {password_change_token}"},
    )
    assert limited_token_attempt.status_code == 401

    password_change = await client.post(
        "/api/v1/auth/cambiar-password-inicial",
        headers={"Authorization": f"Bearer {password_change_token}"},
        json={
            "codigo_verificacion": CODIGO_VERIFICACION,
            "nueva_password": NEW_PASSWORD,
            "confirmar_password": NEW_PASSWORD,
        },
    )

    assert password_change.status_code == 200
    assert password_change.json()["debe_cambiar_password"] is False
    assert password_change.json()["token_type"] == "access"
    assert password_change.json()["access_token"]

    async with session_factory() as session:
        updated = await session.get(Usuario, user_id)
        assert updated is not None
        assert updated.debe_cambiar_password is False
        assert not security.verify_password(DNI_TEMPORAL, updated.password_hash)
        assert security.verify_password(NEW_PASSWORD, updated.password_hash)

        stored_code = await session.scalar(
            select(UsuarioTokenRecuperacion).where(
                UsuarioTokenRecuperacion.token_hash == expected_code_hash
            )
        )
        assert stored_code is not None
        assert stored_code.utilizado_en is not None

        audit = await session.scalar(
            select(Auditoria).where(
                Auditoria.accion == "CAMBIO_PASSWORD_INICIAL",
                Auditoria.id_usuario == user_id,
            )
        )
        assert audit is not None
        audit_data = f"{audit.valor_anterior}{audit.valor_nuevo}".lower()
        assert DNI_TEMPORAL not in audit_data
        assert CODIGO_VERIFICACION not in audit_data
        assert NEW_PASSWORD.lower() not in audit_data

    reused_code = await client.post(
        "/api/v1/auth/cambiar-password-inicial",
        headers={"Authorization": f"Bearer {password_change_token}"},
        json={
            "codigo_verificacion": CODIGO_VERIFICACION,
            "nueva_password": "OtraNueva1!",
            "confirmar_password": "OtraNueva1!",
        },
    )
    assert reused_code.status_code == 401

    old_dni_login = await client.post(
        "/api/v1/auth/login",
        json={"nombre_usuario": "DylanCodip", "password": DNI_TEMPORAL},
    )
    assert old_dni_login.status_code == 401

    normal_login = await client.post(
        "/api/v1/auth/login",
        json={"nombre_usuario": "DylanCodip", "password": NEW_PASSWORD},
    )
    assert normal_login.status_code == 200
    assert normal_login.json()["debe_cambiar_password"] is False
    access_token = normal_login.json()["access_token"]
    assert access_token
    assert security.decode_access_token(access_token)["sub"] == str(user_id)


async def test_codigo_incorrecto_no_modifica_password_ni_estado(
    client,
    session_factory,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        security,
        "generate_initial_verification_code",
        lambda: CODIGO_VERIFICACION,
    )
    async with session_factory() as session:
        role = await create_role(session, "Operador")
        usuario = await create_user(
            session,
            role,
            username="codigo-incorrecto",
            password=DNI_TEMPORAL,
            debe_cambiar_password=True,
        )
        await session.commit()
        user_id = usuario.id_usuario

    login = await client.post(
        "/api/v1/auth/login",
        json={"nombre_usuario": "codigo-incorrecto", "password": DNI_TEMPORAL},
    )
    token = login.json()["password_change_token"]

    response = await client.post(
        "/api/v1/auth/cambiar-password-inicial",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "codigo_verificacion": "000000",
            "nueva_password": NEW_PASSWORD,
            "confirmar_password": NEW_PASSWORD,
        },
    )

    assert response.status_code == 401
    async with session_factory() as session:
        stored = await session.get(Usuario, user_id)
        assert stored is not None
        assert stored.debe_cambiar_password is True
        assert security.verify_password(DNI_TEMPORAL, stored.password_hash)


async def test_codigo_expirado_o_usuario_inactivo_no_permiten_cambio(
    client,
    session_factory,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        security,
        "generate_initial_verification_code",
        lambda: CODIGO_VERIFICACION,
    )
    async with session_factory() as session:
        role = await create_role(session, "Operador")
        usuario = await create_user(
            session,
            role,
            username="codigo-expirado",
            password=DNI_TEMPORAL,
            debe_cambiar_password=True,
        )
        await session.commit()
        user_id = usuario.id_usuario

    login = await client.post(
        "/api/v1/auth/login",
        json={"nombre_usuario": "codigo-expirado", "password": DNI_TEMPORAL},
    )
    token = login.json()["password_change_token"]
    payload = security.decode_password_change_token(token)
    code_hash = security.hash_initial_verification_code(
        token_id=str(payload["jti"]),
        code=CODIGO_VERIFICACION,
    )

    async with session_factory() as session:
        stored_code = await session.scalar(
            select(UsuarioTokenRecuperacion).where(
                UsuarioTokenRecuperacion.token_hash == code_hash
            )
        )
        assert stored_code is not None
        stored_code.expira_en = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    expired = await client.post(
        "/api/v1/auth/cambiar-password-inicial",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "codigo_verificacion": CODIGO_VERIFICACION,
            "nueva_password": NEW_PASSWORD,
            "confirmar_password": NEW_PASSWORD,
        },
    )
    assert expired.status_code == 401

    async with session_factory() as session:
        stored_user = await session.get(Usuario, user_id)
        assert stored_user is not None
        stored_user.estado = False
        stored_code = await session.scalar(
            select(UsuarioTokenRecuperacion).where(
                UsuarioTokenRecuperacion.token_hash == code_hash
            )
        )
        assert stored_code is not None
        stored_code.expira_en = datetime.now(UTC) + timedelta(minutes=10)
        await session.commit()

    inactive = await client.post(
        "/api/v1/auth/cambiar-password-inicial",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "codigo_verificacion": CODIGO_VERIFICACION,
            "nueva_password": NEW_PASSWORD,
            "confirmar_password": NEW_PASSWORD,
        },
    )
    assert inactive.status_code == 401


async def test_login_inicial_envia_codigo_al_correo_configurado(
    session_factory,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        security,
        "generate_initial_verification_code",
        lambda: CODIGO_VERIFICACION,
    )
    outbox: list[tuple[str, str]] = []

    async def notifier(email: str, code: str) -> None:
        outbox.append((email, code))

    async with session_factory() as session:
        role = await create_role(session, "Operador")
        await create_user(
            session,
            role,
            username="dylan",
            email="dylan@codip.pe",
            password=DNI_TEMPORAL,
            debe_cambiar_password=True,
        )
        await session.commit()

        response = await AuthService(
            session,
            initial_password_notifier=notifier,
        ).login(
            LoginRequestDTO(
                nombre_usuario="dylan",
                password=DNI_TEMPORAL,
            )
        )

    assert response.access_token is None
    assert response.codigo_verificacion_requerido is True
    assert outbox == [("dylan@codip.pe", CODIGO_VERIFICACION)]


async def test_codigo_queda_vinculado_al_intento_de_login_que_lo_genero(
    client,
    session_factory,
    monkeypatch,
) -> None:
    generated_codes = iter(("111111", "222222"))
    monkeypatch.setattr(
        security,
        "generate_initial_verification_code",
        lambda: next(generated_codes),
    )
    async with session_factory() as session:
        role = await create_role(session, "Operador")
        await create_user(
            session,
            role,
            username="intentos-separados",
            password=DNI_TEMPORAL,
            debe_cambiar_password=True,
        )
        await session.commit()

    first_login = await client.post(
        "/api/v1/auth/login",
        json={"nombre_usuario": "intentos-separados", "password": DNI_TEMPORAL},
    )
    second_login = await client.post(
        "/api/v1/auth/login",
        json={"nombre_usuario": "intentos-separados", "password": DNI_TEMPORAL},
    )
    first_token = first_login.json()["password_change_token"]
    second_token = second_login.json()["password_change_token"]

    crossed_attempt = await client.post(
        "/api/v1/auth/cambiar-password-inicial",
        headers={"Authorization": f"Bearer {second_token}"},
        json={
            "codigo_verificacion": "111111",
            "nueva_password": NEW_PASSWORD,
            "confirmar_password": NEW_PASSWORD,
        },
    )
    assert crossed_attempt.status_code == 401

    correct_attempt = await client.post(
        "/api/v1/auth/cambiar-password-inicial",
        headers={"Authorization": f"Bearer {first_token}"},
        json={
            "codigo_verificacion": "111111",
            "nueva_password": NEW_PASSWORD,
            "confirmar_password": NEW_PASSWORD,
        },
    )
    assert correct_attempt.status_code == 200


async def test_codigo_se_imprime_en_consola_solo_con_app_debug(
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "app_debug", True)

    await development_initial_password_code_notifier(
        "admin@codip.pe",
        CODIGO_VERIFICACION,
    )

    output = capsys.readouterr().out
    assert "[DEV AUTH]" in output
    assert "a****@codip.pe" in output
    assert CODIGO_VERIFICACION in output

    monkeypatch.setattr(settings, "app_debug", False)
    await development_initial_password_code_notifier(
        "admin@codip.pe",
        "999999",
    )
    assert capsys.readouterr().out == ""
