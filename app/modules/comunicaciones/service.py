from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.auditoria.repository import AuditoriaRepository
from app.modules.comunicaciones.dto import (
    CorreoConfiguracionGlobalResponse,
    CorreoConfiguracionGlobalUpdate,
    CorreoPlantillaHistorialResponse,
    CorreoPlantillaListItem,
    CorreoPlantillaPreviewRequest,
    CorreoPlantillaPreviewResponse,
    CorreoPlantillaResponse,
    CorreoPlantillaRestaurarRequest,
    CorreoPlantillaUpdate,
    CorreoPruebaRequest,
)
from app.modules.comunicaciones.email_service import (
    CodigoAccesoEmail,
    EmailConfigurationError,
    EmailDeliveryError,
    InitialPasswordEmail,
    ParticipanteQrEmail,
    PasswordRecoveryEmail,
    RenderedEmail,
    SMTPEmailSender,
    mask_email,
)
from app.modules.comunicaciones.models import CorreoPlantilla
from app.modules.comunicaciones.repository import ComunicacionRepository
from app.modules.comunicaciones.template_catalog import (
    ACCESO_EMPRESA,
    PRIMER_INGRESO,
    QR_PARTICIPANTE,
    RECUPERACION_PASSWORD,
)
from app.modules.comunicaciones.template_renderer import (
    CorreoTemplateRenderer,
    TemplateValidationError,
)
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.repository import UsuarioRepository


# Código ficticio que se codifica en el QR de los envíos de prueba, para que
# el correo llegue igual que uno real sin exponer un código válido.
CODIGO_QR_DE_PRUEBA = "QR-DE-PRUEBA-SIN-VALIDEZ"


MODULO_COMUNICACIONES = "COMUNICACIONES"


class ComunicacionServiceError(Exception):
    pass


class PlantillaNotFoundError(ComunicacionServiceError):
    pass


class PlantillaInvalidError(ComunicacionServiceError):
    pass


class PlantillaVersionConflictError(ComunicacionServiceError):
    pass


class ConfiguracionCorreoNotFoundError(ComunicacionServiceError):
    pass


class EmisorCorreoInvalidError(ComunicacionServiceError):
    pass


@dataclass(frozen=True, slots=True)
class _Sender:
    email: str
    name: str
    reply_to: str | None
    id_usuario: int | None


class ComunicacionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = ComunicacionRepository(db)
        self.auditoria = AuditoriaRepository(db)
        self.usuarios = UsuarioRepository(db)
        self.renderer = CorreoTemplateRenderer()

    async def listar_plantillas(self) -> list[CorreoPlantillaListItem]:
        plantillas = await self.repository.list_plantillas()
        return [CorreoPlantillaListItem.model_validate(item) for item in plantillas]

    async def obtener_plantilla(self, codigo: str) -> CorreoPlantillaResponse:
        plantilla = await self._get_plantilla(codigo)
        return CorreoPlantillaResponse.model_validate(plantilla)

    async def actualizar_plantilla(
        self,
        *,
        codigo: str,
        data: CorreoPlantillaUpdate,
        actor: Usuario,
    ) -> CorreoPlantillaResponse:
        plantilla = await self._get_plantilla(codigo)
        if data.version_esperada != plantilla.version_actual:
            raise PlantillaVersionConflictError(
                "La plantilla fue modificada por otro usuario; vuelva a cargarla."
            )
        asunto = data.asunto.strip()
        cuerpo_texto = data.cuerpo_texto.strip()
        self._validate_template(
            plantilla=plantilla,
            asunto=asunto,
            cuerpo_html=data.cuerpo_html,
            cuerpo_texto=cuerpo_texto,
        )
        anterior = self._plantilla_values(plantilla)
        nueva_version = plantilla.version_actual + 1
        try:
            await self.repository.update_plantilla(
                plantilla,
                asunto=asunto,
                cuerpo_html=data.cuerpo_html,
                cuerpo_texto=cuerpo_texto,
                estado=data.estado,
                version=nueva_version,
                actualizado_por=actor.id_usuario,
            )
            await self.repository.create_historial(
                plantilla=plantilla,
                version=nueva_version,
                asunto=asunto,
                cuerpo_html=data.cuerpo_html,
                cuerpo_texto=cuerpo_texto,
                motivo=data.motivo.strip(),
                creado_por=actor.id_usuario,
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="correo_plantilla",
                id_entidad=plantilla.id_plantilla,
                accion="ACTUALIZAR_PLANTILLA_CORREO",
                valor_anterior=anterior,
                valor_nuevo=self._plantilla_values(plantilla),
                motivo=data.motivo.strip(),
            )
            await self.db.commit()
            await self.db.refresh(plantilla)
            return CorreoPlantillaResponse.model_validate(plantilla)
        except IntegrityError as exc:
            await self.db.rollback()
            raise PlantillaVersionConflictError(
                "No se pudo guardar la versión porque ya existe."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

    async def previsualizar(
        self,
        *,
        codigo: str,
        data: CorreoPlantillaPreviewRequest,
    ) -> CorreoPlantillaPreviewResponse:
        plantilla = await self._get_plantilla(codigo)
        try:
            asunto, html, texto = self.renderer.render(
                asunto=(data.asunto or plantilla.asunto).strip(),
                cuerpo_html=data.cuerpo_html or plantilla.cuerpo_html,
                cuerpo_texto=(data.cuerpo_texto or plantilla.cuerpo_texto).strip(),
                variables_permitidas=plantilla.variables_permitidas,
                contexto=data.contexto,
            )
        except TemplateValidationError as exc:
            raise PlantillaInvalidError(str(exc)) from exc
        return CorreoPlantillaPreviewResponse(
            asunto=asunto,
            cuerpo_html=html,
            cuerpo_texto=texto,
        )

    async def listar_historial(
        self, codigo: str
    ) -> list[CorreoPlantillaHistorialResponse]:
        plantilla = await self._get_plantilla(codigo)
        historial = await self.repository.list_historial(plantilla.id_plantilla)
        return [
            CorreoPlantillaHistorialResponse.model_validate(item)
            for item in historial
        ]

    async def restaurar_version(
        self,
        *,
        codigo: str,
        version: int,
        data: CorreoPlantillaRestaurarRequest,
        actor: Usuario,
    ) -> CorreoPlantillaResponse:
        plantilla = await self._get_plantilla(codigo)
        if data.version_esperada != plantilla.version_actual:
            raise PlantillaVersionConflictError(
                "La plantilla fue modificada por otro usuario; vuelva a cargarla."
            )
        historial = await self.repository.get_historial_version(
            id_plantilla=plantilla.id_plantilla,
            version=version,
        )
        if historial is None:
            raise PlantillaNotFoundError("La versión solicitada no existe.")
        update = CorreoPlantillaUpdate(
            asunto=historial.asunto,
            cuerpo_html=historial.cuerpo_html,
            cuerpo_texto=historial.cuerpo_texto,
            estado=plantilla.estado,
            version_esperada=plantilla.version_actual,
            motivo=data.motivo,
        )
        return await self.actualizar_plantilla(
            codigo=codigo,
            data=update,
            actor=actor,
        )

    async def obtener_configuracion(self) -> CorreoConfiguracionGlobalResponse:
        configuracion = await self.repository.get_configuracion_global()
        if configuracion is None:
            raise ConfiguracionCorreoNotFoundError(
                "La configuración global de correo no existe."
            )
        emisor = await self.repository.get_usuario(configuracion.id_usuario_emisor)
        if emisor is None:
            raise EmisorCorreoInvalidError("El usuario emisor no existe.")
        return self._config_response(configuracion, emisor.correo)

    async def actualizar_configuracion(
        self,
        *,
        data: CorreoConfiguracionGlobalUpdate,
        actor: Usuario,
    ) -> CorreoConfiguracionGlobalResponse:
        emisor = await self.repository.get_usuario(data.id_usuario_emisor)
        if emisor is None or not emisor.estado or not emisor.correo:
            raise EmisorCorreoInvalidError(
                "El usuario emisor debe existir, estar activo y tener correo."
            )
        nombre = " ".join(data.nombre_remitente.split())
        if "\r" in nombre or "\n" in nombre:
            raise EmisorCorreoInvalidError("El nombre del remitente es inválido.")
        anterior = await self.repository.get_configuracion_global()
        anterior_values = self._config_values(anterior) if anterior else None
        try:
            configuracion = await self.repository.upsert_configuracion_global(
                id_usuario_emisor=emisor.id_usuario,
                nombre_remitente=nombre,
                reply_to=str(data.reply_to) if data.reply_to else None,
                estado=data.estado,
                actualizado_por=actor.id_usuario,
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="correo_configuracion_global",
                id_entidad=configuracion.id_configuracion,
                accion="CONFIGURAR_CORREO_GLOBAL",
                valor_anterior=anterior_values,
                valor_nuevo=self._config_values(configuracion),
            )
            await self.db.commit()
            await self.db.refresh(configuracion)
            return self._config_response(configuracion, emisor.correo)
        except Exception:
            await self.db.rollback()
            raise

    async def enviar_prueba(
        self,
        *,
        codigo: str,
        data: CorreoPruebaRequest,
    ) -> None:
        if not settings.email_enabled:
            raise EmisorCorreoInvalidError(
                "El envío SMTP está deshabilitado en la configuración."
            )
        delivery = CorreoDeliveryService(self.db)
        # La plantilla de QR referencia la imagen embebida (cid:qr_image). Sin
        # adjuntarla, la prueba llega con la imagen rota y no sirve para validar
        # cómo la recibe el participante.
        qr_url = (
            CODIGO_QR_DE_PRUEBA if codigo.upper() == QR_PARTICIPANTE else None
        )
        await delivery.send_template(
            codigo=codigo,
            recipient_email=str(data.destinatario),
            contexto=data.contexto,
            fallback_sender_email="",
            entidad_origen="correo_prueba",
            qr_url=qr_url,
        )
        await self.db.commit()

    async def _get_plantilla(self, codigo: str) -> CorreoPlantilla:
        plantilla = await self.repository.get_plantilla_by_codigo(codigo.upper())
        if plantilla is None:
            raise PlantillaNotFoundError("Plantilla de correo no encontrada.")
        return plantilla

    def _validate_template(
        self,
        *,
        plantilla: CorreoPlantilla,
        asunto: str,
        cuerpo_html: str,
        cuerpo_texto: str,
    ) -> None:
        try:
            self.renderer.validate(
                asunto=asunto,
                cuerpo_html=cuerpo_html,
                cuerpo_texto=cuerpo_texto,
                variables_permitidas=plantilla.variables_permitidas,
            )
        except TemplateValidationError as exc:
            raise PlantillaInvalidError(str(exc)) from exc

    async def _id_modulo(self) -> int | None:
        modulo = await self.usuarios.get_module_by_name(MODULO_COMUNICACIONES)
        return modulo.id_modulo if modulo else None

    @staticmethod
    def _plantilla_values(plantilla: CorreoPlantilla) -> dict[str, object]:
        return {
            "codigo": plantilla.codigo,
            "asunto": plantilla.asunto,
            "version": plantilla.version_actual,
            "estado": plantilla.estado,
        }

    @staticmethod
    def _config_values(configuracion: Any) -> dict[str, object]:
        return {
            "id_usuario_emisor": configuracion.id_usuario_emisor,
            "nombre_remitente": configuracion.nombre_remitente,
            "reply_to": configuracion.reply_to,
            "estado": configuracion.estado,
        }

    @staticmethod
    def _config_response(
        configuracion: Any, correo_emisor: str
    ) -> CorreoConfiguracionGlobalResponse:
        return CorreoConfiguracionGlobalResponse(
            id_configuracion=configuracion.id_configuracion,
            codigo=configuracion.codigo,
            id_usuario_emisor=configuracion.id_usuario_emisor,
            correo_emisor=correo_emisor,
            nombre_remitente=configuracion.nombre_remitente,
            reply_to=configuracion.reply_to,
            estado=configuracion.estado,
            creado_en=configuracion.creado_en,
            actualizado_en=configuracion.actualizado_en,
        )


class CorreoDeliveryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = ComunicacionRepository(db)
        self.renderer = CorreoTemplateRenderer()

    async def notify_initial_password_code(self, data: InitialPasswordEmail) -> None:
        await self._notify_with_console_fallback(
            codigo=PRIMER_INGRESO,
            recipient_email=data.recipient_email,
            contexto={
                "recipient_name": data.recipient_name,
                "code": data.code,
                "expires_minutes": data.expires_minutes,
            },
            fallback_sender_email=data.sender_email,
            console_message=(
                "Código de primer ingreso para "
                f"{mask_email(data.recipient_email)}: {data.code}"
            ),
            entidad_origen="usuario",
        )

    async def notify_password_recovery_code(
        self, data: PasswordRecoveryEmail
    ) -> None:
        await self._notify_with_console_fallback(
            codigo=RECUPERACION_PASSWORD,
            recipient_email=data.recipient_email,
            contexto={
                "recipient_name": data.recipient_name,
                "code": data.code,
                "expires_minutes": data.expires_minutes,
            },
            fallback_sender_email=data.sender_email,
            console_message=(
                "Código de recuperación de contraseña para "
                f"{mask_email(data.recipient_email)}: {data.code}"
            ),
            entidad_origen="usuario",
        )

    async def notify_participante_qr(self, data: ParticipanteQrEmail) -> None:
        await self._notify_with_console_fallback(
            codigo=QR_PARTICIPANTE,
            recipient_email=data.recipient_email,
            # Por seguridad el código nunca viaja en texto: solo dentro del QR.
            contexto={"recipient_name": data.recipient_name},
            fallback_sender_email=data.sender_email,
            console_message=(
                f"QR de ingreso para {mask_email(data.recipient_email)}: "
                f"{data.codigo_seguro}"
            ),
            entidad_origen="participante_qr",
            qr_url=data.codigo_seguro,
        )

    async def notify_codigo_acceso(self, data: CodigoAccesoEmail) -> None:
        await self._notify_with_console_fallback(
            codigo=ACCESO_EMPRESA,
            recipient_email=data.recipient_email,
            contexto={
                "recipient_name": data.recipient_name,
                "nombre_empresa": data.nombre_empresa,
                "nombre_evento": data.nombre_evento,
                "fecha_evento": data.fecha_evento,
                "codigo": data.codigo,
                "expira_en": data.expira_en,
                "portal_url": data.portal_url,
            },
            fallback_sender_email=data.sender_email,
            console_message=(
                f"Código de acceso para {mask_email(data.recipient_email)}: "
                f"{data.codigo}"
            ),
            entidad_origen="codigo_acceso_principal",
        )

    async def _notify_with_console_fallback(
        self,
        *,
        codigo: str,
        recipient_email: str,
        contexto: dict[str, Any],
        fallback_sender_email: str,
        console_message: str,
        entidad_origen: str,
        qr_url: str | None = None,
    ) -> None:
        email_error: EmailDeliveryError | None = None
        if settings.email_enabled:
            try:
                await self.send_template(
                    codigo=codigo,
                    recipient_email=recipient_email,
                    contexto=contexto,
                    fallback_sender_email=fallback_sender_email,
                    entidad_origen=entidad_origen,
                    qr_url=qr_url,
                )
            except EmailDeliveryError as exc:
                email_error = exc

        if settings.email_print_code_to_console:
            print(f"[DEV AUTH] {console_message}", flush=True)

        if email_error is not None and settings.email_print_code_to_console:
            print(
                "[DEV AUTH] El envío SMTP falló; se mantiene el canal de consola.",
                flush=True,
            )
            return
        if email_error is not None:
            raise email_error

    async def send_template(
        self,
        *,
        codigo: str,
        recipient_email: str,
        contexto: dict[str, Any],
        fallback_sender_email: str,
        entidad_origen: str | None = None,
        entidad_id: int | str | None = None,
        qr_url: str | None = None,
    ) -> None:
        plantilla = await self.repository.get_plantilla_by_codigo(codigo)
        if plantilla is None:
            raise EmailConfigurationError(
                f"La plantilla de correo {codigo} no está configurada."
            )
        if not plantilla.estado:
            raise EmailConfigurationError(
                f"La plantilla de correo {codigo} está inactiva."
            )
        sender = await self._resolve_sender(fallback_sender_email)
        try:
            asunto, html, texto = self.renderer.render(
                asunto=plantilla.asunto,
                cuerpo_html=plantilla.cuerpo_html,
                cuerpo_texto=plantilla.cuerpo_texto,
                variables_permitidas=plantilla.variables_permitidas,
                contexto=contexto,
            )
        except TemplateValidationError as exc:
            raise EmailConfigurationError(str(exc)) from exc

        try:
            await SMTPEmailSender().send_rendered(
                RenderedEmail(
                    sender_email=sender.email,
                    recipient_email=recipient_email,
                    subject=asunto,
                    plain_text=texto,
                    html=html,
                    from_name=sender.name,
                    reply_to=sender.reply_to,
                    qr_url=qr_url,
                )
            )
            await self.repository.create_envio(
                plantilla=plantilla,
                id_usuario_emisor=sender.id_usuario,
                destinatario=recipient_email,
                asunto=asunto,
                entidad_origen=entidad_origen,
                entidad_id=entidad_id,
                estado="ENVIADO",
            )
        except EmailDeliveryError as exc:
            await self.repository.create_envio(
                plantilla=plantilla,
                id_usuario_emisor=sender.id_usuario,
                destinatario=recipient_email,
                asunto=asunto,
                entidad_origen=entidad_origen,
                entidad_id=entidad_id,
                estado="FALLIDO",
                error_detalle=str(exc)[:500],
            )
            raise

    async def _resolve_sender(self, fallback_sender_email: str) -> _Sender:
        configuracion = await self.repository.get_configuracion_global()
        if configuracion is None:
            if not fallback_sender_email:
                raise EmailConfigurationError(
                    "La configuración global de correo no existe."
                )
            return _Sender(
                email=fallback_sender_email,
                name=settings.email_from_name,
                reply_to=None,
                id_usuario=None,
            )
        if not configuracion.estado:
            raise EmailConfigurationError(
                "La configuración global de correo está inactiva."
            )
        emisor = await self.repository.get_usuario(configuracion.id_usuario_emisor)
        if emisor is None or not emisor.estado or not emisor.correo:
            raise EmailConfigurationError(
                "El usuario emisor de correo no está disponible."
            )
        return _Sender(
            email=emisor.correo,
            name=configuracion.nombre_remitente,
            reply_to=configuracion.reply_to,
            id_usuario=emisor.id_usuario,
        )
