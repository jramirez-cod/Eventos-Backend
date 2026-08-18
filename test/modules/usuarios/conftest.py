from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from itertools import count
import os
from uuid import uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-usuarios-module")
os.environ.setdefault("PASSWORD_HASH_ARGON2_TIME_COST", "1")
os.environ.setdefault("PASSWORD_HASH_ARGON2_MEMORY_COST", "1024")
os.environ.setdefault("PASSWORD_HASH_ARGON2_PARALLELISM", "1")
os.environ["EMAIL_ENABLED"] = "false"
os.environ["EMAIL_PRINT_CODE_TO_CONSOLE"] = "false"

from app.core import security  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.auditoria.models import Auditoria  # noqa: E402
from app.modules.usuarios.models import (  # noqa: E402
    Modulo,
    Permiso,
    Rol,
    RolPermisoModulo,
    TipoDocumento,
    Usuario,
    UsuarioTokenRecuperacion,
)


VALID_PASSWORD = "Password1!"
NEW_PASSWORD = "NuevaPass1!"

_numero_documento_seq = count(10_000_001)


def _next_numero_documento() -> str:
    return str(next(_numero_documento_seq))


@pytest_asyncio.fixture()
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    schema_name = f"test_usuarios_{uuid4().hex}"
    admin_engine = create_async_engine(settings.database_url, echo=False)
    async with admin_engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema_name}"'))

    engine = create_async_engine(
        settings.database_url,
        echo=False,
        connect_args={"options": f"-csearch_path={schema_name}"},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autoflush=False,
        expire_on_commit=False,
    )

    yield factory

    await engine.dispose()
    async with admin_engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA "{schema_name}" CASCADE'))
    await admin_engine.dispose()


@pytest_asyncio.fixture()
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()


async def create_role(
    session: AsyncSession,
    nombre_rol: str,
    *,
    estado: bool = True,
) -> Rol:
    rol = Rol(nombre_rol=nombre_rol, estado=estado)
    session.add(rol)
    await session.flush()
    return rol


async def create_tipo_documento(
    session: AsyncSession,
    *,
    nombre_documento: str = "DNI",
    longitud: int | None = 8,
    estado: bool = True,
) -> TipoDocumento:
    tipo_documento = TipoDocumento(
        nombre_documento=nombre_documento, longitud=longitud, estado=estado
    )
    session.add(tipo_documento)
    await session.flush()
    return tipo_documento


async def create_user(
    session: AsyncSession,
    rol: Rol,
    *,
    username: str,
    email: str | None = None,
    password: str = VALID_PASSWORD,
    estado: bool = True,
    debe_cambiar_password: bool = False,
    tipo_documento: TipoDocumento | None = None,
    numero_documento: str | None = None,
) -> Usuario:
    if tipo_documento is None:
        tipo_documento = await create_tipo_documento(session)
    usuario = Usuario(
        id_rol=rol.id_rol,
        id_tipo_documento=tipo_documento.id_tipo_documento,
        numero_documento=numero_documento or _next_numero_documento(),
        nombre_usuario=username,
        password_hash=security.hash_password(password),
        nombres="Juan",
        apellidos="Prueba",
        correo=email or f"{username}@codip.pe",
        estado=estado,
        debe_cambiar_password=debe_cambiar_password,
    )
    session.add(usuario)
    await session.flush()
    return usuario


async def grant_permission(
    session: AsyncSession,
    rol: Rol,
    *,
    permiso_nombre: str,
    modulo_nombre: str = "USUARIOS",
) -> None:
    modulo = await session.scalar(
        select(Modulo).where(Modulo.nombre_modulo == modulo_nombre)
    )
    if modulo is None:
        modulo = Modulo(nombre_modulo=modulo_nombre, estado=True)
        session.add(modulo)

    permiso = await session.scalar(select(Permiso).where(Permiso.codigo == permiso_nombre))
    if permiso is None:
        permiso = Permiso(
            codigo=permiso_nombre,
            nombre_permiso=permiso_nombre.replace("_", " ").title(),
            estado=True,
        )
        session.add(permiso)

    await session.flush()
    session.add(
        RolPermisoModulo(
            id_rol=rol.id_rol,
            id_modulo=modulo.id_modulo,
            id_permiso=permiso.id_permiso,
        )
    )
    await session.flush()


async def create_recovery_token(
    session: AsyncSession,
    usuario: Usuario,
    *,
    token: str = "recovery-token",
    expira_en: datetime | None = None,
    utilizado_en: datetime | None = None,
) -> str:
    stored = UsuarioTokenRecuperacion(
        id_usuario=usuario.id_usuario,
        token_hash=security.hash_recovery_token(token),
        expira_en=expira_en or datetime.now(UTC) + timedelta(minutes=30),
        utilizado_en=utilizado_en,
    )
    session.add(stored)
    await session.flush()
    return token


async def create_initial_password_challenge(
    session: AsyncSession,
    usuario: Usuario,
    *,
    code: str = "482913",
    expira_en: datetime | None = None,
    utilizado_en: datetime | None = None,
) -> tuple[str, str]:
    password_change_token = security.create_password_change_token(
        usuario.id_usuario
    )
    payload = security.decode_password_change_token(password_change_token)
    stored = UsuarioTokenRecuperacion(
        id_usuario=usuario.id_usuario,
        token_hash=security.hash_initial_verification_code(
            token_id=str(payload["jti"]),
            code=code,
        ),
        expira_en=expira_en or datetime.now(UTC) + timedelta(minutes=10),
        utilizado_en=utilizado_en,
    )
    session.add(stored)
    await session.flush()
    return password_change_token, code


async def seed_admin_with_permissions(session: AsyncSession) -> tuple[Rol, Usuario]:
    admin_role = await create_role(session, "Administrador de Eventos")
    await grant_permission(
        session, admin_role, permiso_nombre="CREAR_USUARIO", modulo_nombre="USUARIOS"
    )
    await grant_permission(
        session, admin_role, permiso_nombre="INACTIVAR_USUARIO", modulo_nombre="USUARIOS"
    )
    admin = await create_user(
        session,
        admin_role,
        username="admin",
        email="admin@codip.pe",
        debe_cambiar_password=False,
    )
    await session.commit()
    return admin_role, admin


def access_token(usuario: Usuario) -> str:
    return security.create_access_token(
        usuario.id_usuario,
        usuario.id_rol,
        usuario.nombre_usuario,
        usuario.nombres,
        usuario.apellidos,
        usuario.correo,
    )


def auth_header(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token(usuario)}"}


__all__ = [
    "Auditoria",
    "NEW_PASSWORD",
    "VALID_PASSWORD",
    "access_token",
    "auth_header",
    "create_recovery_token",
    "create_initial_password_challenge",
    "create_role",
    "create_tipo_documento",
    "create_user",
    "seed_admin_with_permissions",
]
