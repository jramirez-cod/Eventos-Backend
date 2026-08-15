from datetime import UTC, datetime

from sqlalchemy import Select, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.modules.usuarios.models import (
    Modulo,
    Permiso,
    Rol,
    RolPermisoModulo,
    Usuario,
    UsuarioTokenRecuperacion,
)


class UsuarioRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, id_usuario: int) -> Usuario | None:
        stmt = (
            select(Usuario)
            .options(joinedload(Usuario.rol))
            .where(Usuario.id_usuario == id_usuario)
        )
        return await self.db.scalar(stmt)

    async def get_by_username(self, nombre_usuario: str) -> Usuario | None:
        stmt = select(Usuario).where(func.lower(Usuario.nombre_usuario) == nombre_usuario.lower())
        return await self.db.scalar(stmt)

    async def get_by_email(self, correo: str) -> Usuario | None:
        stmt = select(Usuario).where(func.lower(Usuario.correo) == correo.lower())
        return await self.db.scalar(stmt)

    async def get_role(self, id_rol: int) -> Rol | None:
        return await self.db.get(Rol, id_rol)

    async def get_role_by_name(self, nombre_rol: str) -> Rol | None:
        stmt = select(Rol).where(func.upper(Rol.nombre_rol) == nombre_rol.upper())
        return await self.db.scalar(stmt)

    async def get_module_by_name(self, nombre_modulo: str) -> Modulo | None:
        stmt = select(Modulo).where(func.upper(Modulo.nombre_modulo) == nombre_modulo.upper())
        return await self.db.scalar(stmt)

    async def get_permission_by_name(self, nombre_permiso: str) -> Permiso | None:
        stmt = select(Permiso).where(func.upper(Permiso.codigo) == nombre_permiso.upper())
        return await self.db.scalar(stmt)

    async def create_user(
        self,
        *,
        id_rol: int,
        nombre_usuario: str,
        password_hash: str,
        nombres: str,
        apellidos: str,
        correo: str,
        estado: bool = True,
        debe_cambiar_password: bool = True,
    ) -> Usuario:
        usuario = Usuario(
            id_rol=id_rol,
            nombre_usuario=nombre_usuario,
            password_hash=password_hash,
            nombres=nombres,
            apellidos=apellidos,
            correo=correo,
            estado=estado,
            debe_cambiar_password=debe_cambiar_password,
        )
        self.db.add(usuario)
        await self.db.flush()
        await self.db.refresh(usuario)
        return usuario

    async def update_password(self, usuario: Usuario, password_hash: str) -> Usuario:
        usuario.password_hash = password_hash
        await self.db.flush()
        return usuario

    async def update_last_login(self, usuario: Usuario) -> Usuario:
        usuario.ultimo_acceso = datetime.now(UTC)
        await self.db.flush()
        return usuario

    async def mark_initial_password_changed(self, usuario: Usuario) -> Usuario:
        usuario.debe_cambiar_password = False
        await self.db.flush()
        return usuario

    async def deactivate_user(self, usuario: Usuario) -> Usuario:
        usuario.estado = False
        await self.db.flush()
        return usuario

    async def activate_user(self, usuario: Usuario) -> Usuario:
        usuario.estado = True
        await self.db.flush()
        return usuario

    async def create_recovery_token(
        self,
        *,
        usuario: Usuario,
        token_hash: str,
        expira_en: datetime,
    ) -> UsuarioTokenRecuperacion:
        token = UsuarioTokenRecuperacion(
            id_usuario=usuario.id_usuario,
            token_hash=token_hash,
            expira_en=expira_en,
        )
        self.db.add(token)
        await self.db.flush()
        return token

    async def get_recovery_token_by_hash(self, token_hash: str) -> UsuarioTokenRecuperacion | None:
        stmt = select(UsuarioTokenRecuperacion).where(
            UsuarioTokenRecuperacion.token_hash == token_hash
        )
        return await self.db.scalar(stmt)

    async def mark_recovery_token_used(self, token: UsuarioTokenRecuperacion) -> UsuarioTokenRecuperacion:
        token.utilizado_en = datetime.now(UTC)
        await self.db.flush()
        return token

    async def has_permission(self, *, id_rol: int, modulo: str, permiso: str) -> bool:
        stmt: Select[tuple[bool]] = select(
            exists().where(
                RolPermisoModulo.id_rol == id_rol,
                RolPermisoModulo.id_modulo == Modulo.id_modulo,
                Modulo.estado.is_(True),
                func.upper(Modulo.nombre_modulo) == modulo.upper(),
                RolPermisoModulo.id_permiso == Permiso.id_permiso,
                Permiso.estado.is_(True),
                func.upper(Permiso.codigo) == permiso.upper(),
            )
        )
        return bool(await self.db.scalar(stmt))

    async def list_all(self) -> list[Usuario]:
        stmt = (
            select(Usuario)
            .options(joinedload(Usuario.rol))
            .order_by(Usuario.creado_en.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_roles(self) -> list[Rol]:
        stmt = select(Rol).where(Rol.estado.is_(True)).order_by(Rol.nombre_rol)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
