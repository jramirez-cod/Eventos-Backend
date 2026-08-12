from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.modules.auditoria.repository import AuditoriaRepository
from app.modules.usuarios.dto import (
    CambioPasswordInicialRequestDTO,
    LoginRequestDTO,
    LoginResponseDTO,
    RecuperarPasswordRequestDTO,
    RecuperarPasswordResponseDTO,
    RestablecerPasswordRequestDTO,
)
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.repository import UsuarioRepository


RECOVERY_ACCEPTED_MESSAGE = (
    "Si existe una cuenta asociada, se enviarán las instrucciones de recuperación."
)

PasswordRecoveryNotifier = Callable[[str, str], Awaitable[None]]


class AuthServiceError(Exception):
    pass


class InvalidCredentialsError(AuthServiceError):
    pass


class InactiveUserError(AuthServiceError):
    pass


class InvalidPasswordChangeTokenError(AuthServiceError):
    pass


class PasswordMismatchError(AuthServiceError):
    pass


class PasswordPolicyViolationError(AuthServiceError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("La contraseña no cumple la política configurada.")


class InvalidRecoveryTokenError(AuthServiceError):
    pass


async def noop_password_recovery_notifier(_: str, __: str) -> None:
    """
    Punto de integración para el futuro módulo comunicaciones.

    Recibe correo y token en claro, pero no lo registra ni lo persiste.
    """


class AuthService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        recovery_notifier: PasswordRecoveryNotifier = noop_password_recovery_notifier,
    ) -> None:
        self.db = db
        self.usuarios = UsuarioRepository(db)
        self.auditoria = AuditoriaRepository(db)
        self.recovery_notifier = recovery_notifier

    async def login(self, data: LoginRequestDTO) -> LoginResponseDTO:
        usuario = await self.usuarios.get_by_username(data.nombre_usuario)
        if usuario is None or not security.verify_password(
            data.password, usuario.password_hash
        ):
            raise InvalidCredentialsError("Credenciales inválidas.")

        if not usuario.estado:
            raise InactiveUserError("Usuario inactivo.")

        if usuario.debe_cambiar_password:
            token = security.create_password_change_token(usuario.id_usuario)
            return LoginResponseDTO(
                debe_cambiar_password=True,
                token_type=security.PASSWORD_CHANGE_TOKEN_TYPE,
                password_change_token=token,
            )

        await self.usuarios.update_last_login(usuario)
        await self.db.commit()
        return LoginResponseDTO(
            debe_cambiar_password=False,
            token_type=security.ACCESS_TOKEN_TYPE,
            access_token=security.create_access_token(usuario.id_usuario),
        )

    async def cambiar_password_inicial(
        self,
        *,
        token: str,
        data: CambioPasswordInicialRequestDTO,
    ) -> LoginResponseDTO:
        if data.nueva_password != data.confirmar_password:
            raise PasswordMismatchError("Las contraseñas no coinciden.")

        self._validate_password_policy(data.nueva_password)

        usuario = await self._get_user_from_password_change_token(token)
        if not usuario.estado or not usuario.debe_cambiar_password:
            raise InvalidPasswordChangeTokenError("Token inválido.")

        try:
            await self.usuarios.update_password(
                usuario, security.hash_password(data.nueva_password)
            )
            await self.usuarios.mark_initial_password_changed(usuario)
            await self.usuarios.update_last_login(usuario)
            await self.auditoria.create(
                id_usuario=usuario.id_usuario,
                entidad="usuario",
                id_entidad=usuario.id_usuario,
                accion="CAMBIO_PASSWORD_INICIAL",
                valor_anterior={"debe_cambiar_password": True},
                valor_nuevo={"debe_cambiar_password": False},
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

        return LoginResponseDTO(
            debe_cambiar_password=False,
            token_type=security.ACCESS_TOKEN_TYPE,
            access_token=security.create_access_token(usuario.id_usuario),
        )

    async def solicitar_recuperacion(
        self,
        data: RecuperarPasswordRequestDTO,
    ) -> RecuperarPasswordResponseDTO:
        usuario = await self.usuarios.get_by_email(str(data.correo))
        response = RecuperarPasswordResponseDTO(message=RECOVERY_ACCEPTED_MESSAGE)
        if usuario is None or not usuario.estado:
            return response

        token = security.generate_recovery_token()
        token_hash = security.hash_recovery_token(token)
        expira_en = datetime.now(UTC) + timedelta(
            minutes=settings.recovery_token_expire_minutes
        )

        try:
            stored_token = await self.usuarios.create_recovery_token(
                usuario=usuario,
                token_hash=token_hash,
                expira_en=expira_en,
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

        if stored_token is not None:
            await self.recovery_notifier(usuario.correo, token)
        return response

    async def restablecer_password(
        self,
        data: RestablecerPasswordRequestDTO,
    ) -> LoginResponseDTO:
        if data.nueva_password != data.confirmar_password:
            raise PasswordMismatchError("Las contraseñas no coinciden.")

        self._validate_password_policy(data.nueva_password)
        token_hash = security.hash_recovery_token(data.token)
        recovery_token = await self.usuarios.get_recovery_token_by_hash(token_hash)
        if recovery_token is None:
            raise InvalidRecoveryTokenError("Token inválido.")

        usuario = await self.usuarios.get_by_id(recovery_token.id_usuario)
        if (
            recovery_token.utilizado_en is not None
            or self._is_expired(recovery_token.expira_en)
            or usuario is None
            or not usuario.estado
        ):
            raise InvalidRecoveryTokenError("Token inválido.")

        try:
            debe_cambiar_password_anterior = usuario.debe_cambiar_password
            await self.usuarios.update_password(
                usuario, security.hash_password(data.nueva_password)
            )
            if usuario.debe_cambiar_password:
                await self.usuarios.mark_initial_password_changed(usuario)
            await self.usuarios.mark_recovery_token_used(recovery_token)
            await self.usuarios.update_last_login(usuario)
            await self.auditoria.create(
                id_usuario=usuario.id_usuario,
                entidad="usuario",
                id_entidad=usuario.id_usuario,
                accion="RESTABLECIMIENTO_PASSWORD",
                valor_anterior={
                    "debe_cambiar_password": debe_cambiar_password_anterior
                },
                valor_nuevo={
                    "password_actualizado": True,
                    "debe_cambiar_password": usuario.debe_cambiar_password,
                },
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

        return LoginResponseDTO(
            debe_cambiar_password=usuario.debe_cambiar_password,
            token_type=security.ACCESS_TOKEN_TYPE,
            access_token=security.create_access_token(usuario.id_usuario),
        )

    async def _get_user_from_password_change_token(self, token: str) -> Usuario:
        try:
            payload = security.decode_password_change_token(token)
            id_usuario = int(payload["sub"])
        except (ValueError, security.InvalidTokenError) as exc:
            raise InvalidPasswordChangeTokenError("Token inválido.") from exc

        usuario = await self.usuarios.get_by_id(id_usuario)
        if usuario is None:
            raise InvalidPasswordChangeTokenError("Token inválido.")
        return usuario

    @staticmethod
    def _validate_password_policy(password: str) -> None:
        try:
            security.validate_password_policy(password)
        except security.PasswordPolicyError as exc:
            raise PasswordPolicyViolationError(exc.errors) from exc

    @staticmethod
    def _is_expired(expira_en: datetime) -> bool:
        if expira_en.tzinfo is None:
            expira_en = expira_en.replace(tzinfo=UTC)
        return expira_en <= datetime.now(UTC)
