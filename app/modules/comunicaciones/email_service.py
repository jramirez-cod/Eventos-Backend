import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime, formataddr, make_msgid
from io import BytesIO
from pathlib import Path
import smtplib
import ssl

from jinja2 import Environment, FileSystemLoader, select_autoescape
import qrcode

from app.core.config import settings


INITIAL_PASSWORD_SUBJECT = (
    "Código de verificación para configurar tu acceso | Sistema Eventos CODIP"
)
PASSWORD_RECOVERY_SUBJECT = (
    "Código de verificación para recuperar tu contraseña | Sistema Eventos CODIP"
)
PARTICIPANTE_QR_SUBJECT = "Tu código de ingreso al evento | Sistema Eventos CODIP"
CODIGO_ACCESO_SUBJECT = "Código de acceso para gestionar participantes | Sistema Eventos CODIP"
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


@dataclass(frozen=True, slots=True)
class PasswordRecoveryEmail:
    sender_email: str
    recipient_email: str
    recipient_name: str
    code: str
    expires_minutes: int


@dataclass(frozen=True, slots=True)
class ParticipanteQrEmail:
    sender_email: str
    recipient_email: str
    recipient_name: str
    codigo_seguro: str


@dataclass(frozen=True, slots=True)
class CodigoAccesoEmail:
    sender_email: str
    recipient_email: str
    recipient_name: str
    nombre_empresa: str
    codigo: str
    portal_url: str
    # Identifican de qué evento es el código y hasta cuándo sirve: sin esto dos
    # correos de empresas homónimas resultaban indistinguibles.
    nombre_evento: str = ""
    fecha_evento: str = ""
    expira_en: str = ""


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    sender_email: str
    recipient_email: str
    subject: str
    plain_text: str
    html: str
    from_name: str
    reply_to: str | None = None
    qr_url: str | None = None


QR_IMAGE_CID = "qr_image"
QR_IMAGE_FILENAME = "codigo-qr-ingreso.png"


def build_qr_png(contenido: str) -> bytes:
    """Genera el QR como PNG RGB.

    `qrcode.make(...)` produce un PNG de 1 bit (modo "1"); varios clientes y
    proxies de imagen (Gmail entre ellos) no lo renderizan embebido y lo
    degradan a un adjunto suelto con la imagen rota en el cuerpo. Un PNG RGB
    convencional se muestra en todos.
    """
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(contenido)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white").get_image()
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def embed_qr_image(message: EmailMessage, contenido: str) -> None:
    """Embebe el QR en la alternativa HTML como `cid:qr_image`.

    Debe llamarse después de `add_alternative(html)`. Deja la estructura
    multipart/alternative → multipart/related(type=text/html) → [html, png]:
    - `type="text/html"` es obligatorio según RFC 2387 y algunos clientes lo
      usan para ubicar la parte raíz;
    - `Content-Disposition: inline` con nombre de archivo evita que el cliente
      lo trate como adjunto genérico y da un nombre legible si el usuario lo
      guarda.
    """
    html_part = message.get_payload()[-1]
    html_part.add_related(
        build_qr_png(contenido),
        maintype="image",
        subtype="png",
        cid=f"<{QR_IMAGE_CID}>",
        filename=QR_IMAGE_FILENAME,
        disposition="inline",
    )
    # Tras add_related, html_part pasa a ser el contenedor multipart/related.
    html_part.set_param("type", "text/html")


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

    async def send_password_recovery_code(
        self,
        data: PasswordRecoveryEmail,
    ) -> None:
        message = self._build_password_recovery_message(data)
        await asyncio.to_thread(self._send_message, message, data.sender_email)

    async def send_participante_qr(
        self,
        data: ParticipanteQrEmail,
    ) -> None:
        message = self._build_participante_qr_message(data)
        await asyncio.to_thread(self._send_message, message, data.sender_email)

    async def send_codigo_acceso(
        self,
        data: CodigoAccesoEmail,
    ) -> None:
        message = self._build_codigo_acceso_message(data)
        await asyncio.to_thread(self._send_message, message, data.sender_email)

    async def send_rendered(self, data: RenderedEmail) -> None:
        message = self._build_rendered_message(data)
        await asyncio.to_thread(self._send_message, message, data.sender_email)

    @staticmethod
    def _build_rendered_message(data: RenderedEmail) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = data.subject
        message["From"] = formataddr((data.from_name, data.sender_email))
        message["To"] = data.recipient_email
        if data.reply_to:
            message["Reply-To"] = data.reply_to
        message.set_content(data.plain_text)
        message.add_alternative(data.html, subtype="html")
        if data.qr_url:
            embed_qr_image(message, data.qr_url)
        return message

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

    def _build_password_recovery_message(
        self,
        data: PasswordRecoveryEmail,
    ) -> EmailMessage:
        html = self.templates.get_template(
            "password_recovery_code.html"
        ).render(
            recipient_name=data.recipient_name,
            code=data.code,
            expires_minutes=data.expires_minutes,
        )
        plain_text = (
            f"Hola, {data.recipient_name}.\n\n"
            "Tu código para recuperar la contraseña del Sistema Eventos "
            f"CODIP es: {data.code}\n\n"
            f"El código vence en {data.expires_minutes} minutos. "
            "Si no solicitaste esta operación, comunícate con el "
            "administrador del sistema."
        )

        message = EmailMessage()
        message["Subject"] = PASSWORD_RECOVERY_SUBJECT
        message["From"] = formataddr(
            (settings.email_from_name, data.sender_email)
        )
        message["To"] = data.recipient_email
        message.set_content(plain_text)
        message.add_alternative(html, subtype="html")
        return message

    def _build_participante_qr_message(
        self,
        data: ParticipanteQrEmail,
    ) -> EmailMessage:
        html = self.templates.get_template("participante_qr.html").render(
            recipient_name=data.recipient_name,
        )
        plain_text = (
            f"Hola, {data.recipient_name}.\n\n"
            "Adjuntamos tu código QR de ingreso al evento. Preséntalo "
            "(impreso o desde tu celular) en la entrada para que puedan "
            "escanearlo."
        )

        message = EmailMessage()
        message["Subject"] = PARTICIPANTE_QR_SUBJECT
        message["From"] = formataddr((settings.email_from_name, data.sender_email))
        message["To"] = data.recipient_email
        message.set_content(plain_text)
        message.add_alternative(html, subtype="html")
        embed_qr_image(message, data.codigo_seguro)
        return message

    def _build_codigo_acceso_message(
        self,
        data: CodigoAccesoEmail,
    ) -> EmailMessage:
        html = self.templates.get_template("codigo_acceso_principal.html").render(
            recipient_name=data.recipient_name,
            nombre_empresa=data.nombre_empresa,
            codigo=data.codigo,
            portal_url=data.portal_url,
        )
        plain_text = (
            f"Hola, {data.recipient_name}.\n\n"
            f"Te compartimos el código de acceso para gestionar a los "
            f"participantes de {data.nombre_empresa} en el Sistema Eventos "
            f"CODIP: {data.codigo}\n\n"
            f"Ingresa aquí: {data.portal_url}"
        )

        message = EmailMessage()
        message["Subject"] = CODIGO_ACCESO_SUBJECT
        message["From"] = formataddr((settings.email_from_name, data.sender_email))
        message["To"] = data.recipient_email
        message.set_content(plain_text)
        message.add_alternative(html, subtype="html")
        return message

    @staticmethod
    def _ensure_delivery_headers(message: EmailMessage, sender_email: str) -> None:
        """Completa `Date` y `Message-ID` si faltan.

        Los filtros antispam penalizan mensajes sin estas cabeceras; y un
        correo clasificado como spam no muestra ninguna imagen embebida
        (Gmail las bloquea), así que el QR llega "roto".
        """
        if "Date" not in message:
            message["Date"] = format_datetime(datetime.now(timezone.utc))
        if "Message-ID" not in message:
            domain = sender_email.rsplit("@", 1)[-1] if "@" in sender_email else None
            message["Message-ID"] = make_msgid(domain=domain)

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
                self._ensure_delivery_headers(message, sender_email)
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


async def notify_password_recovery_code(data: PasswordRecoveryEmail) -> None:
    email_error: EmailDeliveryError | None = None
    if settings.email_enabled:
        try:
            await SMTPEmailSender().send_password_recovery_code(data)
        except EmailDeliveryError as exc:
            email_error = exc

    if settings.email_print_code_to_console:
        masked_email = mask_email(data.recipient_email)
        print(
            f"[DEV AUTH] Código de recuperación de contraseña para {masked_email}: {data.code}",
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


async def notify_participante_qr(data: ParticipanteQrEmail) -> None:
    email_error: EmailDeliveryError | None = None
    if settings.email_enabled:
        try:
            await SMTPEmailSender().send_participante_qr(data)
        except EmailDeliveryError as exc:
            email_error = exc

    if settings.email_print_code_to_console:
        masked_email = mask_email(data.recipient_email)
        print(
            f"[DEV AUTH] QR de ingreso para {masked_email}: {data.codigo_seguro}",
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


async def notify_codigo_acceso(data: CodigoAccesoEmail) -> None:
    email_error: EmailDeliveryError | None = None
    if settings.email_enabled:
        try:
            await SMTPEmailSender().send_codigo_acceso(data)
        except EmailDeliveryError as exc:
            email_error = exc

    if settings.email_print_code_to_console:
        masked_email = mask_email(data.recipient_email)
        print(
            f"[DEV AUTH] Código de acceso para {masked_email}: {data.codigo}",
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
