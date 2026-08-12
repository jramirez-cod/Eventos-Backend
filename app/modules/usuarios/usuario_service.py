from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.modules.auditoria.repository import AuditoriaRepository
from app.modules.usuarios.dto import InactivarUsuarioDTO, UsuarioCreateDTO
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.repository import UsuarioRepository


class UsuarioServiceError(Exception):
    pass


class RolNotFoundError(UsuarioServiceError):
    pass


class DuplicateUsernameError(UsuarioServiceError):
    pass


class DuplicateEmailError(UsuarioServiceError):
    pass


class UsuarioNotFoundError(UsuarioServiceError):
    pass


class PasswordPolicyViolationError(UsuarioServiceError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("La contraseña no cumple la política configurada.")


class UsuarioService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.usuarios = UsuarioRepository(db)
        self.auditoria = AuditoriaRepository(db)

    async def crear_usuario(
        self,
        *,
        data: UsuarioCreateDTO,
        actor: Usuario,
    ) -> Usuario:
        rol = await self.usuarios.get_role(data.id_rol)
        if rol is None or not rol.estado:
            raise RolNotFoundError("Rol no encontrado.")

        if await self.usuarios.get_by_username(data.nombre_usuario):
            raise DuplicateUsernameError("Nombre de usuario ya existe.")

        if await self.usuarios.get_by_email(str(data.correo)):
            raise DuplicateEmailError("Correo ya existe.")

        self._validate_password_policy(data.password_temporal)

        try:
            usuario = await self.usuarios.create_user(
                id_rol=data.id_rol,
                nombre_usuario=data.nombre_usuario,
                nombres=data.nombres,
                apellidos=data.apellidos,
                correo=str(data.correo),
                password_hash=security.hash_password(data.password_temporal),
                estado=True,
                debe_cambiar_password=True,
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                entidad="usuario",
                id_entidad=usuario.id_usuario,
                accion="CREACION_USUARIO",
                valor_nuevo={
                    "id_usuario": usuario.id_usuario,
                    "nombre_usuario": usuario.nombre_usuario,
                    "correo": usuario.correo,
                    "id_rol": usuario.id_rol,
                    "estado": usuario.estado,
                    "debe_cambiar_password": usuario.debe_cambiar_password,
                },
            )
            await self.db.commit()
            await self.db.refresh(usuario)
            return usuario
        except Exception:
            await self.db.rollback()
            raise

    async def inactivar_usuario(
        self,
        *,
        id_usuario: int,
        data: InactivarUsuarioDTO,
        actor: Usuario,
    ) -> Usuario:
        usuario = await self.usuarios.get_by_id(id_usuario)
        if usuario is None:
            raise UsuarioNotFoundError("Usuario no encontrado.")

        anterior = {"estado": usuario.estado}
        try:
            await self.usuarios.deactivate_user(usuario)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                entidad="usuario",
                id_entidad=usuario.id_usuario,
                accion="INACTIVACION_USUARIO",
                valor_anterior=anterior,
                valor_nuevo={"estado": usuario.estado},
                motivo=data.motivo,
            )
            await self.db.commit()
            await self.db.refresh(usuario)
            return usuario
        except Exception:
            await self.db.rollback()
            raise

    @staticmethod
    def _validate_password_policy(password: str) -> None:
        try:
            security.validate_password_policy(password)
        except security.PasswordPolicyError as exc:
            raise PasswordPolicyViolationError(exc.errors) from exc
