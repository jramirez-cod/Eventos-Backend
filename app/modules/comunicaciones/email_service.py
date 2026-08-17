import asyncio
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
import smtplib
import ssl

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings


INITIAL_PASSWORD_SUBJECT = (
    "Código de verificación para configurar tu acceso | Sistema Eventos CODIP"
)
TEMPLATE_DIRECTORY = Path(__file__).resolve().parent / "templates"


class EmailDeliveryError(RuntimeError):
    pass


class EmailConfigurationError(EmailDeliveryError):
    pass


@dataclass(frozen=True, slots=True)
class InitialPasswordEmail:
    sender_email: str
    recipient_email: str
    recipient_name: str
    code: str
    expires_minutes: int


class SMTPEmailSender:
    def __init__(self) -> None:
        self.templates = Environment(
            loader=FileSystemLoader(TEMPLATE_DIRECTORY),
            autoescape=select_autoescape(("html", "xml")),
        )

    async def send_initial_password_code(
        self,
        data: InitialPasswordEmail,
    ) -> None:
        message = self._build_initial_password_message(data)
        await asyncio.to_thread(self._send_message, message, data.sender_email)

    def _build_initial_password_message(
        self,
        data: InitialPasswordEmail,
    ) -> EmailMessage:
        html = self.templates.get_template(
            "initial_password_code.html"
        ).render(
            recipient_name=data.recipient_name,
            code=data.code,
            expires_minutes=data.expires_minutes,
        )
        plain_text = (
            f"Hola, {data.recipient_name}.\n\n"
            "Tu código para configurar la contraseña del Sistema Eventos "
            f"CODIP es: {data.code}\n\n"
            f"El código vence en {data.expires_minutes} minutos. "
            "Si no solicitaste esta operación, comunícate con el "
            "administrador del sistema."
        )

        message = EmailMessage()
        message["Subject"] = INITIAL_PASSWORD_SUBJECT
        message["From"] = formataddr(
            (settings.email_from_name, data.sender_email)
        )
        message["To"] = data.recipient_email
        message.set_content(plain_text)
        message.add_alternative(html, subtype="html")
        return message

    def _send_message(
        self,
        message: EmailMessage,
        sender_email: str,
    ) -> None:
        password = settings.smtp_app_password.get_secret_value().replace(" ", "")
        if not password:
            raise EmailConfigurationError(
                "SMTP_APP_PASSWORD no está configurado."
            )
        if not sender_email:
            raise EmailConfigurationError(
                "El correo remitente no está configurado."
            )

        try:
            with smtplib.SMTP(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
            ) as smtp:
                smtp.ehlo()
                if settings.smtp_starttls:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                smtp.login(sender_email, password)
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailDeliveryError(
                "No se pudo entregar el correo de verificación."
            ) from exc


async def notify_initial_password_code(data: InitialPasswordEmail) -> None:
    email_error: EmailDeliveryError | None = None
    if settings.email_enabled:
        try:
            await SMTPEmailSender().send_initial_password_code(data)
        except EmailDeliveryError as exc:
            email_error = exc

    if settings.email_print_code_to_console:
        masked_email = mask_email(data.recipient_email)
        print(
            f"[DEV AUTH] Código de primer ingreso para {masked_email}: {data.code}",
            flush=True,
        )

    if email_error is not None and settings.email_print_code_to_console:
        print(
            "[DEV AUTH] El envío SMTP falló; se mantiene el canal de consola.",
            flush=True,
        )
        return
    if email_error is not None:
        raise email_error


def mask_email(email: str) -> str:
    local_part, separator, domain = email.partition("@")
    if not separator:
        return "***"
    visible = local_part[:1]
    return f"{visible}{'*' * max(3, len(local_part) - 1)}@{domain}"
