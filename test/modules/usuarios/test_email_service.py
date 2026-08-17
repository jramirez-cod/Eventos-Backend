from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.core.config import settings
from app.modules.comunicaciones.email_service import (
    INITIAL_PASSWORD_SUBJECT,
    EmailDeliveryError,
    InitialPasswordEmail,
    SMTPEmailSender,
    notify_initial_password_code,
)
from app.modules.usuarios.auth_service import (
    AuthService,
    VerificationEmailDeliveryError,
)
from app.modules.usuarios.dto import LoginRequestDTO
from app.modules.usuarios.models import UsuarioTokenRecuperacion
from test.modules.usuarios.conftest import create_role, create_user


pytestmark = pytest.mark.asyncio


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host: str, port: int, timeout: int) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.login_args: tuple[str, str] | None = None
        self.message = None
        self.starttls_called = False
        self.__class__.instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def ehlo(self) -> None:
        return None

    def starttls(self, *, context) -> None:
        self.starttls_called = context is not None

    def login(self, email: str, password: str) -> None:
        self.login_args = (email, password)

    def send_message(self, message) -> None:
        self.message = message


def email_data() -> InitialPasswordEmail:
    return InitialPasswordEmail(
        sender_email="codipcorporativo@gmail.com",
        recipient_email="dylan@codip.pe",
        recipient_name="Dylan Codip",
        code="482913",
        expires_minutes=10,
    )


async def test_smtp_construye_correo_html_y_texto_con_tls(
    monkeypatch,
) -> None:
    FakeSMTP.instances.clear()
    monkeypatch.setattr(
        "app.modules.comunicaciones.email_service.smtplib.SMTP",
        FakeSMTP,
    )
    monkeypatch.setattr(settings, "smtp_app_password", SecretStr("abcd efgh"))
    monkeypatch.setattr(settings, "smtp_starttls", True)

    await SMTPEmailSender().send_initial_password_code(email_data())

    smtp = FakeSMTP.instances[0]
    assert smtp.host == "smtp.gmail.com"
    assert smtp.port == 587
    assert smtp.starttls_called is True
    assert smtp.login_args == ("codipcorporativo@gmail.com", "abcdefgh")
    assert smtp.message["Subject"] == INITIAL_PASSWORD_SUBJECT
    assert smtp.message["To"] == "dylan@codip.pe"
    assert "codipcorporativo@gmail.com" in smtp.message["From"]

    body = smtp.message.get_body(preferencelist=("html",)).get_content()
    assert "Dylan Codip" in body
    assert "482913" in body
    assert "10 minutos" in body


async def test_fallo_smtp_mantiene_consola_como_respaldo(
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "email_enabled", True)
    monkeypatch.setattr(settings, "email_print_code_to_console", True)
    monkeypatch.setattr(
        SMTPEmailSender,
        "send_initial_password_code",
        AsyncMock(side_effect=EmailDeliveryError("SMTP no disponible")),
    )

    await notify_initial_password_code(email_data())

    output = capsys.readouterr().out
    assert "d****@codip.pe" in output
    assert "482913" in output
    assert "El envío SMTP falló" in output


async def test_fallo_de_entrega_sin_consola_invalida_el_desafio(
    session_factory,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "email_enabled", True)
    monkeypatch.setattr(settings, "email_print_code_to_console", False)
    monkeypatch.setattr(settings, "email_sender_user_id", 1)

    async def failing_notifier(_: InitialPasswordEmail) -> None:
        raise EmailDeliveryError("SMTP no disponible")

    async with session_factory() as session:
        role = await create_role(session, "Operador correo")
        await create_user(
            session,
            role,
            username="admin-correo",
            email="codipcorporativo@gmail.com",
        )
        await create_user(
            session,
            role,
            username="usuario-correo",
            email="usuario@codip.pe",
            password="74859632",
            debe_cambiar_password=True,
        )
        await session.commit()

        with pytest.raises(VerificationEmailDeliveryError):
            await AuthService(
                session,
                initial_password_notifier=failing_notifier,
            ).login(
                LoginRequestDTO(
                    nombre_usuario="usuario-correo",
                    password="74859632",
                )
            )

    async with session_factory() as session:
        token = await session.scalar(select(UsuarioTokenRecuperacion))
        assert token is not None
        assert token.utilizado_en is not None
