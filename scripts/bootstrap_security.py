import argparse
import asyncio
from getpass import getpass
from os import getenv
from pathlib import Path
import sys

# Fix para Windows: usar SelectorEventLoop en lugar de ProactorEventLoop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import inspect, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core import security  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.modules.usuarios.models import (  # noqa: E402
    Modulo,
    Permiso,
    Rol,
    RolPermisoModulo,
    Usuario,
)

ROLE_ADMIN = "ADMINISTRADOR_EVENTOS"
ROLE_USER = "Usuario Interno"
MODULE_USUARIOS = "usuarios"
PERMISSIONS_USUARIOS = ("CREAR_USUARIO", "INACTIVAR_USUARIO")
REQUIRED_TABLES = {
    "rol",
    "usuario",
    "modulo",
    "permiso",
    "rol_permiso_modulo",
}


async def _ensure_schema_exists() -> None:
    async with engine.connect() as conn:
        table_names = await conn.run_sync(
            lambda sync_conn: set(inspect(sync_conn).get_table_names())
        )

    missing = REQUIRED_TABLES - table_names
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise RuntimeError(
            "No se puede ejecutar bootstrap: faltan tablas requeridas "
            f"({missing_list}). Este script no crea ni modifica el esquema."
        )


async def _get_or_create_role(nombre_rol: str) -> Rol:
    async with AsyncSessionLocal() as session:
        rol = await session.scalar(select(Rol).where(Rol.nombre_rol == nombre_rol))
        if rol is None:
            rol = Rol(
                nombre_rol=nombre_rol,
                descripcion=nombre_rol.replace("_", " ").title(),
                estado=True,
            )
            session.add(rol)
            await session.commit()
            await session.refresh(rol)
        elif not rol.estado:
            rol.estado = True
            await session.commit()
            await session.refresh(rol)
        return rol


async def _get_or_create_module() -> Modulo:
    async with AsyncSessionLocal() as session:
        modulo = await session.scalar(
            select(Modulo).where(Modulo.nombre_modulo == MODULE_USUARIOS)
        )
        if modulo is None:
            modulo = Modulo(
                nombre_modulo=MODULE_USUARIOS,
                descripcion="Administración de acceso y usuarios",
                estado=True,
            )
            session.add(modulo)
            await session.commit()
            await session.refresh(modulo)
        elif not modulo.estado:
            modulo.estado = True
            await session.commit()
            await session.refresh(modulo)
        return modulo


async def _get_or_create_permission(nombre_permiso: str) -> Permiso:
    async with AsyncSessionLocal() as session:
        permiso = await session.scalar(select(Permiso).where(Permiso.codigo == nombre_permiso))
        if permiso is None:
            permiso = Permiso(
                codigo=nombre_permiso,
                nombre_permiso=nombre_permiso.replace("_", " ").title(),
                descripcion=f"Permite {nombre_permiso.replace('_', ' ').lower()}",
                estado=True,
            )
            session.add(permiso)
            await session.commit()
            await session.refresh(permiso)
        elif not permiso.estado:
            permiso.estado = True
            await session.commit()
            await session.refresh(permiso)
        return permiso


async def _ensure_role_permission(
    *,
    rol: Rol,
    modulo: Modulo,
    permiso: Permiso,
) -> None:
    async with AsyncSessionLocal() as session:
        relation = await session.scalar(
            select(RolPermisoModulo).where(
                RolPermisoModulo.id_rol == rol.id_rol,
                RolPermisoModulo.id_modulo == modulo.id_modulo,
                RolPermisoModulo.id_permiso == permiso.id_permiso,
            )
        )
        if relation is None:
            session.add(
                RolPermisoModulo(
                    id_rol=rol.id_rol,
                    id_modulo=modulo.id_modulo,
                    id_permiso=permiso.id_permiso,
                )
            )
            await session.commit()


async def _ensure_admin_user(
    *,
    rol: Rol,
    username: str,
    password: str,
    email: str,
    nombres: str,
    apellidos: str,
) -> Usuario:
    security.validate_password_policy(password)
    async with AsyncSessionLocal() as session:
        existing = await session.scalar(
            select(Usuario).where(Usuario.nombre_usuario == username)
        )
        if existing is not None:
            changed = False
            if not existing.estado:
                existing.estado = True
                changed = True
            if existing.id_rol != rol.id_rol:
                existing.id_rol = rol.id_rol
                changed = True
            if changed:
                await session.commit()
                await session.refresh(existing)
            return existing

        admin = Usuario(
            id_rol=rol.id_rol,
            nombre_usuario=username,
            password_hash=security.hash_password(password),
            nombres=nombres,
            apellidos=apellidos,
            correo=email,
            estado=True,
            debe_cambiar_password=False,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        return admin


def _resolve_admin_args(args: argparse.Namespace) -> dict[str, str]:
    username = args.username or getenv("BOOTSTRAP_ADMIN_USERNAME")
    email = args.email or getenv("BOOTSTRAP_ADMIN_EMAIL")
    nombres = args.nombres or getenv("BOOTSTRAP_ADMIN_NOMBRES") or "Administrador"
    apellidos = args.apellidos or getenv("BOOTSTRAP_ADMIN_APELLIDOS") or "Eventos"
    password = getenv("BOOTSTRAP_ADMIN_PASSWORD")

    if not username:
        username = input("Usuario administrador: ").strip()
    if not email:
        email = input("Correo administrador: ").strip()
    if not password:
        password = getpass("Password administrador: ")

    if not username or not email or not password:
        raise ValueError("Usuario, correo y password administrador son obligatorios.")

    return {
        "username": username,
        "password": password,
        "email": email,
        "nombres": nombres,
        "apellidos": apellidos,
    }


async def bootstrap(args: argparse.Namespace) -> None:
    await _ensure_schema_exists()
    admin_args = _resolve_admin_args(args)
    admin_role = await _get_or_create_role(ROLE_ADMIN)
    await _get_or_create_role(ROLE_USER)
    usuarios_module = await _get_or_create_module()

    for permission_name in PERMISSIONS_USUARIOS:
        permission = await _get_or_create_permission(permission_name)
        await _ensure_role_permission(
            rol=admin_role,
            modulo=usuarios_module,
            permiso=permission,
        )

    admin = await _ensure_admin_user(rol=admin_role, **admin_args)
    print(
        "Bootstrap de seguridad completado. "
        f"Administrador: {admin.nombre_usuario} (id={admin.id_usuario})."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap de seguridad inicial.")
    parser.add_argument("--username", help="Nombre de usuario del primer administrador.")
    parser.add_argument("--email", help="Correo del primer administrador.")
    parser.add_argument("--nombres", help="Nombres del primer administrador.")
    parser.add_argument("--apellidos", help="Apellidos del primer administrador.")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(bootstrap(parse_args()))
