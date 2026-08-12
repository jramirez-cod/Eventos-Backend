import pytest

from test.modules.usuarios.conftest import (
    VALID_PASSWORD,
    create_role,
    create_user,
)


pytestmark = pytest.mark.asyncio


async def test_login_correcto_usuario_con_password_definitiva(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        rol = await create_role(session, "Operador")
        usuario = await create_user(
            session,
            rol,
            username="jperez",
            debe_cambiar_password=False,
        )
        await session.commit()
        user_id = usuario.id_usuario

    response = await client.post(
        "/api/v1/auth/login",
        json={"nombre_usuario": "jperez", "password": VALID_PASSWORD},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["debe_cambiar_password"] is False
    assert body["token_type"] == "access"
    assert body["access_token"]
    assert body["password_change_token"] is None

    async with session_factory() as session:
        stored = await session.get(type(usuario), user_id)
        assert stored.id_usuario == user_id


async def test_password_incorrecto_y_usuario_inexistente_responden_generico(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        rol = await create_role(session, "Operador")
        await create_user(session, rol, username="jperez")
        await session.commit()

    bad_password = await client.post(
        "/api/v1/auth/login",
        json={"nombre_usuario": "jperez", "password": "PasswordMala1!"},
    )
    missing_user = await client.post(
        "/api/v1/auth/login",
        json={"nombre_usuario": "noexiste", "password": "PasswordMala1!"},
    )

    assert bad_password.status_code == 401
    assert missing_user.status_code == 401
    assert bad_password.json()["detail"] == missing_user.json()["detail"]


async def test_usuario_inactivo_no_puede_iniciar_sesion(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        rol = await create_role(session, "Operador")
        await create_user(session, rol, username="inactivo", estado=False)
        await session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"nombre_usuario": "inactivo", "password": VALID_PASSWORD},
    )

    assert response.status_code == 401


async def test_usuario_con_password_temporal_recibe_token_limitado(
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

    response = await client.post(
        "/api/v1/auth/login",
        json={"nombre_usuario": "temporal", "password": VALID_PASSWORD},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["debe_cambiar_password"] is True
    assert body["token_type"] == "password_change"
    assert body["access_token"] is None
    assert body["password_change_token"]

    async with session_factory() as session:
        stored = await session.get(type(usuario), user_id)
        assert stored.ultimo_acceso is None


async def test_oauth_token_para_swagger_devuelve_bearer_token(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        rol = await create_role(session, "Operador")
        await create_user(
            session,
            rol,
            username="swagger",
            debe_cambiar_password=False,
        )
        await session.commit()

    response = await client.post(
        "/api/v1/auth/token",
        data={"username": "swagger", "password": VALID_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
