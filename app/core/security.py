from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import secrets
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import settings


ACCESS_TOKEN_TYPE = "access"
PASSWORD_CHANGE_TOKEN_TYPE = "password_change"

_password_hash = PasswordHash(
    (
        Argon2Hasher(
            time_cost=settings.password_hash_argon2_time_cost,
            memory_cost=settings.password_hash_argon2_memory_cost,
            parallelism=settings.password_hash_argon2_parallelism,
        ),
    )
)


class InvalidTokenError(ValueError):
    pass


class PasswordPolicyError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("La contraseña no cumple la política configurada.")


class TemporaryPasswordPolicyError(ValueError):
    pass


def _require_secret() -> str:
    if not settings.secret_key:
        raise RuntimeError("SECRET_KEY no está configurado.")
    return settings.secret_key


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    return _password_hash.verify(password, password_hash)


def validate_password_policy(password: str) -> None:
    errors: list[str] = []

    if len(password) < settings.password_min_length:
        errors.append(
            f"La contraseña debe tener al menos {settings.password_min_length} caracteres."
        )
    if settings.password_require_uppercase and not any(c.isupper() for c in password):
        errors.append("La contraseña debe incluir al menos una mayúscula.")
    if settings.password_require_lowercase and not any(c.islower() for c in password):
        errors.append("La contraseña debe incluir al menos una minúscula.")
    if settings.password_require_number and not any(c.isdigit() for c in password):
        errors.append("La contraseña debe incluir al menos un número.")
    if settings.password_require_special and not any(not c.isalnum() for c in password):
        errors.append("La contraseña debe incluir al menos un carácter especial.")

    if errors:
        raise PasswordPolicyError(errors)


def validate_temporary_dni_password(password: str) -> None:
    is_valid_dni = (
        len(password) == settings.temporary_dni_length
        and password.isascii()
        and password.isdigit()
    )
    if not is_valid_dni:
        raise TemporaryPasswordPolicyError(
            "La contraseña temporal debe ser un DNI de "
            f"{settings.temporary_dni_length} dígitos."
        )


def _create_token(
    *,
    subject: int,
    token_type: str,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + expires_delta,
        "token_type": token_type,
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, _require_secret(), algorithm=settings.jwt_algorithm)


def create_access_token(
    id_usuario: int,
    id_rol: int,
    nombre_usuario: str = "",
    nombres: str = "",
    apellidos: str = "",
) -> str:
    return _create_token(
        subject=id_usuario,
        token_type=ACCESS_TOKEN_TYPE,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        extra_claims={
            "id_usuario": id_usuario,
            "id_rol": id_rol,
            "nombre_usuario": nombre_usuario,
            "nombres": nombres,
            "apellidos": apellidos,
        },
    )


def create_password_change_token(id_usuario: int) -> str:
    return _create_token(
        subject=id_usuario,
        token_type=PASSWORD_CHANGE_TOKEN_TYPE,
        expires_delta=timedelta(minutes=settings.password_change_token_expire_minutes),
        extra_claims={"jti": secrets.token_urlsafe(24)},
    )


def decode_token(token: str, expected_token_type: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            _require_secret(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError("Token inválido.") from exc

    if payload.get("token_type") != expected_token_type:
        raise InvalidTokenError("Tipo de token inválido.")

    if "sub" not in payload:
        raise InvalidTokenError("Token inválido.")

    return payload


def decode_access_token(token: str) -> dict[str, Any]:
    return decode_token(token, ACCESS_TOKEN_TYPE)


def decode_password_change_token(token: str) -> dict[str, Any]:
    return decode_token(token, PASSWORD_CHANGE_TOKEN_TYPE)


def generate_recovery_token() -> str:
    return secrets.token_urlsafe(48)


def generate_initial_verification_code() -> str:
    length = settings.initial_password_code_length
    return f"{secrets.randbelow(10**length):0{length}d}"


def hash_recovery_token(token: str) -> str:
    digest = hmac.new(
        _require_secret().encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest


def hash_initial_verification_code(*, token_id: str, code: str) -> str:
    return hash_recovery_token(f"initial_password:{token_id}:{code}")


def recovery_token_matches(token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_recovery_token(token), token_hash)
