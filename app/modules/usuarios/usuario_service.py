from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.modules.auditoria.repository import AuditoriaRepository
from app.modules.usuarios.dto import InactivarUsuarioDTO, UsuarioCreateDTO, UsuarioUpdateDTO
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.repository import UsuarioRepository


MODULO_USUARIOS = "USUARIOS"


class UsuarioServiceError(Exception):
    pass


class RolNotFoundError(UsuarioServiceError):
    pass


class TipoDocumentoNotFoundError(UsuarioServiceError):
    pass


class DuplicateUsernameError(UsuarioServiceError):
    pass


class DuplicateEmailError(UsuarioServiceError):
    pass


class DuplicateDocumentoError(UsuarioServiceError):
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

    async def crear_usuario(self, *, data: UsuarioCreateDTO, actor: Usuario) -> Usuario:
        rol = await self.usuarios.get_role(data.id_rol)
        if rol is None or not rol.estado:
            raise RolNotFoundError("Rol no encontrado.")

        tipo_documento = await self.usuarios.get_tipo_documento(data.id_tipo_documento)
        if tipo_documento is None or not tipo_documento.estado:
            raise TipoDocumentoNotFoundError("Tipo de documento no encontrado.")

        if await self.usuarios.get_by_username(data.nombre_usuario):
            raise DuplicateUsernameError("Nombre de usuario ya existe.")

        if await self.usuarios.get_by_email(str(data.correo)):
            raise DuplicateEmailError("Correo ya existe.")

        if await self.usuarios.get_by_numero_documento(data.numero_documento):
            raise DuplicateDocumentoError("Número de documento ya existe.")

        self._validate_numero_documento(data.numero_documento, tipo_documento.longitud)

        id_modulo = await self._id_modulo()

        try:
            usuario = await self.usuarios.create_user(
                id_rol=data.id_rol,
                id_tipo_documento=data.id_tipo_documento,
                numero_documento=data.numero_documento,
                nombre_usuario=data.nombre_usuario,
                nombres=data.nombres,
                apellidos=data.apellidos,
                correo=str(data.correo),
                password_hash=security.hash_password(data.numero_documento),
                estado=True,
                debe_cambiar_password=True,
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=id_modulo,
                entidad="usuario",
                id_entidad=usuario.id_usuario,
                accion="CREACION_USUARIO",
                valor_nuevo={
                    "id_usuario": usuario.id_usuario,
                    "nombre_usuario": usuario.nombre_usuario,
                    "correo": usuario.correo,
                    "id_rol": usuario.id_rol,
                    "id_tipo_documento": usuario.id_tipo_documento,
                    "numero_documento": usuario.numero_documento,
                    "estado": usuario.estado,
                    "debe_cambiar_password": usuario.debe_cambiar_password,
                },
            )
            await self.db.commit()
            usuario_con_rol = await self.usuarios.get_by_id(usuario.id_usuario)
            return usuario_con_rol or usuario
        except Exception:
            await self.db.rollback()
            raise

    async def obtener_usuario(self, id_usuario: int) -> Usuario:
        usuario = await self.usuarios.get_by_id(id_usuario)
        if usuario is None:
            raise UsuarioNotFoundError("Usuario no encontrado.")
        return usuario

    async def actualizar_usuario(
        self, *, id_usuario: int, data: UsuarioUpdateDTO, actor: Usuario
    ) -> Usuario:
        usuario = await self.usuarios.get_by_id(id_usuario)
        if usuario is None:
            raise UsuarioNotFoundError("Usuario no encontrado.")

        rol = await self.usuarios.get_role(data.id_rol)
        if rol is None or not rol.estado:
            raise RolNotFoundError("Rol no encontrado.")

        tipo_documento = await self.usuarios.get_tipo_documento(data.id_tipo_documento)
        if tipo_documento is None or not tipo_documento.estado:
            raise TipoDocumentoNotFoundError("Tipo de documento no encontrado.")

        existente_correo = await self.usuarios.get_by_email(str(data.correo))
        if existente_correo is not None and existente_correo.id_usuario != id_usuario:
            raise DuplicateEmailError("Correo ya existe.")

        existente_documento = await self.usuarios.get_by_numero_documento(data.numero_documento)
        if existente_documento is not None and existente_documento.id_usuario != id_usuario:
            raise DuplicateDocumentoError("Número de documento ya existe.")

        self._validate_numero_documento(data.numero_documento, tipo_documento.longitud)

        anterior = {
            "id_rol": usuario.id_rol,
            "id_tipo_documento": usuario.id_tipo_documento,
            "numero_documento": usuario.numero_documento,
            "nombres": usuario.nombres,
            "apellidos": usuario.apellidos,
            "correo": usuario.correo,
        }
        id_modulo = await self._id_modulo()
        try:
            await self.usuarios.update_user(
                usuario,
                id_rol=data.id_rol,
                id_tipo_documento=data.id_tipo_documento,
                numero_documento=data.numero_documento,
                nombres=data.nombres,
                apellidos=data.apellidos,
                correo=str(data.correo),
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=id_modulo,
                entidad="usuario",
                id_entidad=usuario.id_usuario,
                accion="ACTUALIZACION_USUARIO",
                valor_anterior=anterior,
                valor_nuevo={
                    "id_rol": usuario.id_rol,
                    "id_tipo_documento": usuario.id_tipo_documento,
                    "numero_documento": usuario.numero_documento,
                    "nombres": usuario.nombres,
                    "apellidos": usuario.apellidos,
                    "correo": usuario.correo,
                },
            )
            await self.db.commit()
            usuario_con_rol = await self.usuarios.get_by_id(usuario.id_usuario)
            return usuario_con_rol or usuario
        except Exception:
            await self.db.rollback()
            raise

    async def inactivar_usuario(
        self, *, id_usuario: int, data: InactivarUsuarioDTO, actor: Usuario
    ) -> Usuario:
        usuario = await self.usuarios.get_by_id(id_usuario)
        if usuario is None:
            raise UsuarioNotFoundError("Usuario no encontrado.")

        anterior = {"estado": usuario.estado}
        id_modulo = await self._id_modulo()
        try:
            await self.usuarios.deactivate_user(usuario)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=id_modulo,
                entidad="usuario",
                id_entidad=usuario.id_usuario,
                accion="INACTIVACION_USUARIO",
                valor_anterior=anterior,
                valor_nuevo={"estado": usuario.estado},
                motivo=data.motivo,
            )
            await self.db.commit()
            usuario_con_rol = await self.usuarios.get_by_id(usuario.id_usuario)
            return usuario_con_rol or usuario
        except Exception:
            await self.db.rollback()
            raise

    async def activar_usuario(self, *, id_usuario: int, actor: Usuario) -> Usuario:
        usuario = await self.usuarios.get_by_id(id_usuario)
        if usuario is None:
            raise UsuarioNotFoundError("Usuario no encontrado.")

        anterior = {"estado": usuario.estado}
        id_modulo = await self._id_modulo()
        try:
            await self.usuarios.activate_user(usuario)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=id_modulo,
                entidad="usuario",
                id_entidad=usuario.id_usuario,
                accion="ACTIVACION_USUARIO",
                valor_anterior=anterior,
                valor_nuevo={"estado": usuario.estado},
            )
            await self.db.commit()
            usuario_con_rol = await self.usuarios.get_by_id(usuario.id_usuario)
            return usuario_con_rol or usuario
        except Exception:
            await self.db.rollback()
            raise

    async def _id_modulo(self) -> int | None:
        modulo = await self.usuarios.get_module_by_name(MODULO_USUARIOS)
        return modulo.id_modulo if modulo else None

    @staticmethod
    def _validate_numero_documento(numero_documento: str, longitud: int | None) -> None:
        try:
            security.validate_document_number(numero_documento, longitud=longitud)
        except security.TemporaryPasswordPolicyError as exc:
            raise PasswordPolicyViolationError([str(exc)]) from exc
