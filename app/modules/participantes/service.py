from datetime import date, datetime, time, timezone
import math
import secrets
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    generate_portal_code,
    hash_portal_code,
    verify_password,
)
from app.modules.auditoria.repository import AuditoriaRepository
from app.modules.comunicaciones.email_service import (
    CodigoAccesoEmail,
    EmailDeliveryError,
    ParticipanteQrEmail,
)
from app.modules.comunicaciones.service import CorreoDeliveryService
from app.modules.contactos.service import ContactoService
from app.modules.empresas.models import Empresa
from app.modules.eventos.models import ProgramacionEvento
from app.modules.eventos.repository import EventoRepository
from app.modules.eventos.service import (
    EventoNotEditableError,
    EventoService,
    ProgramacionNotEditableError,
)
from app.modules.maestros.models import Beneficio, TipoCalculoBeneficio
from app.modules.maestros.repository import MaestroRepository
from app.modules.participantes.beneficio_evaluador import (
    calcular_cupo_restante,
    hay_cupo_disponible,
)
from app.modules.participantes.dto import (
    AsignarBeneficioRequest,
    BeneficioDisponibleResponse,
    ContactoDesdeEventoCreate,
    EnviarCodigoAccesoMasivoResponse,
    EnviarQrMasivoResponse,
    EscaneoQrResponse,
    EventoContactoCreateMultiple,
    EventoContactoCreateResponse,
    EventoContactoListResponse,
    EventoContactoResponse,
    EventoEmpresaResponse,
    InvitadoCreate,
    ReimprimirCredencialRequest,
)
from app.modules.participantes.models import (
    EventoContacto,
    EventoEmpresa,
    ParticipanteQr,
)
from app.modules.participantes.repository import (
    EventoContactoDetalle,
    EventoEmpresaDetalle,
    ParticipanteRepository,
)
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.repository import UsuarioRepository


MODULO_PARTICIPANTES = "PARTICIPANTES"
LIMITE_INVITADOS_SIN_REGISTRAR = 20
PERU_TIMEZONE = ZoneInfo("America/Lima")
# CorreoDeliveryService resuelve el remitente desde la configuración global
# persistida; el campo del DTO solo actúa como respaldo cuando no existe.
SENDER_DESDE_CONFIGURACION = ""


class ParticipanteServiceError(Exception):
    pass


class ProgramacionNotFoundError(ParticipanteServiceError):
    pass


class EventoNotOpenError(ParticipanteServiceError):
    pass


class EmpresaNotFoundError(ParticipanteServiceError):
    pass


class EmpresaInactiveError(ParticipanteServiceError):
    pass


class EventoEmpresaNotFoundError(ParticipanteServiceError):
    pass


class DuplicateEventoEmpresaError(ParticipanteServiceError):
    pass


class ContactoNotFoundError(ParticipanteServiceError):
    pass


class ContactoInactiveError(ParticipanteServiceError):
    pass


class ContactoSinEmpresaAfiliadaError(ParticipanteServiceError):
    pass


class DuplicateEventoContactoError(ParticipanteServiceError):
    pass


class EventoContactoNotFoundError(ParticipanteServiceError):
    pass


class ParticipantePersistenceConflictError(ParticipanteServiceError):
    pass


class ParticipanteBeneficioNotFoundError(ParticipanteServiceError):
    pass


class AsignacionBeneficioCantidadInvalidaError(ParticipanteServiceError):
    pass


class AsignacionBeneficioGrupoInvalidoError(ParticipanteServiceError):
    pass


class AsignacionBeneficioExistenteError(ParticipanteServiceError):
    pass


class AsignacionBeneficioNotFoundError(ParticipanteServiceError):
    pass


class BeneficioNoAplicableError(ParticipanteServiceError):
    pass


class CupoBeneficioAgotadoError(ParticipanteServiceError):
    pass


class ParticipanteQrNotFoundError(ParticipanteServiceError):
    pass


class CredencialYaImpresaError(ParticipanteServiceError):
    pass


class ResponsableInvalidoError(ParticipanteServiceError):
    pass


class PasswordIncorrectoError(ParticipanteServiceError):
    pass


class ContactoPrincipalInvalidoError(ParticipanteServiceError):
    pass


class LimiteInvitadosSuperadoError(ParticipanteServiceError):
    pass


class InvitadoInvalidoError(ParticipanteServiceError):
    pass


class InvitadoDatosConflictoError(ParticipanteServiceError):
    pass


class InvitadoDuplicadoEnProgramacionError(ParticipanteServiceError):
    pass


class ProgramacionSinDiasError(ParticipanteServiceError):
    pass


class CodigoAccesoYaVencidoError(ParticipanteServiceError):
    pass


class ParticipanteService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.participantes = ParticipanteRepository(db)
        self.contactos = ContactoService(db)
        self.usuarios = UsuarioRepository(db)
        self.auditoria = AuditoriaRepository(db)
        self.maestros = MaestroRepository(db)
        self.eventos = EventoRepository(db)
        self.correo = CorreoDeliveryService(db)

    # -- EventoEmpresa -----------------------------------------------

    async def afiliar_empresa_evento(
        self, *, id_programacion_evento: int, id_empresa: int, actor: Usuario
    ) -> EventoEmpresaResponse:
        await self._get_open_programacion(id_programacion_evento)
        await self._get_active_company(id_empresa)
        existente = await self.participantes.get_evento_empresa(
            id_programacion_evento=id_programacion_evento, id_empresa=id_empresa
        )
        if existente is not None and existente.estado:
            raise DuplicateEventoEmpresaError(
                "La empresa ya está afiliada a este evento."
            )

        try:
            if existente is not None:
                evento_empresa = await self.participantes.set_evento_empresa_estado(
                    existente, estado=True
                )
                accion = "REAFILIAR_EMPRESA_EVENTO"
            else:
                evento_empresa = await self.participantes.create_evento_empresa(
                    id_programacion_evento=id_programacion_evento,
                    id_empresa=id_empresa,
                )
                accion = "AFILIAR_EMPRESA_EVENTO"
            contacto_principal = await self.contactos.contactos.get_contacto_principal(
                id_empresa
            )
            if contacto_principal is not None:
                await self.participantes.set_contacto_principal(
                    evento_empresa, id_contacto=contacto_principal.id_contacto
                )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento_empresa",
                id_entidad=evento_empresa.id_evento_empresa,
                accion=accion,
                valor_nuevo=self._evento_empresa_values(evento_empresa),
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise DuplicateEventoEmpresaError(
                "La empresa ya está afiliada a este evento."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

        return await self._get_evento_empresa_response(
            evento_empresa.id_evento_empresa,
            id_programacion_evento=id_programacion_evento,
        )

    async def desafiliar_empresa(
        self,
        *,
        id_evento_empresa: int,
        motivo: str | None,
        actor: Usuario,
        id_programacion_evento: int | None = None,
    ) -> None:
        evento_empresa = await self.participantes.get_evento_empresa_by_id(
            id_evento_empresa,
            id_programacion_evento=id_programacion_evento,
            for_update=True,
        )
        if evento_empresa is None:
            raise EventoEmpresaNotFoundError("Afiliación no encontrada.")
        await self._get_open_programacion(evento_empresa.id_programacion_evento)

        anterior = self._evento_empresa_values(evento_empresa)
        try:
            await self.participantes.invalidar_codigos(id_evento_empresa)
            contactos = await self.participantes.list_evento_contactos_activos_por_empresa(
                id_programacion_evento=evento_empresa.id_programacion_evento,
                id_empresa=evento_empresa.id_empresa,
            )
            for contacto in contactos:
                await self.participantes.update_evento_contacto(
                    contacto, {"estado": False}
                )
                qr = await self.participantes.get_participante_qr_by_evento_contacto(
                    contacto.id_evento_contacto
                )
                if qr is not None:
                    qr.estado = False
                    await self.db.flush()
            await self.participantes.set_evento_empresa_estado(
                evento_empresa, estado=False
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento_empresa",
                id_entidad=id_evento_empresa,
                accion="DESAFILIAR_EMPRESA_EVENTO",
                valor_anterior=anterior,
                valor_nuevo=self._evento_empresa_values(evento_empresa),
                motivo=motivo,
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

    async def listar_empresas_programacion(
        self, id_programacion_evento: int
    ) -> list[EventoEmpresaResponse]:
        if await self.participantes.get_programacion(id_programacion_evento) is None:
            raise ProgramacionNotFoundError("Programación no encontrada.")
        rows = await self.participantes.list_empresas_programacion(
            id_programacion_evento
        )
        return [self._evento_empresa_response(row) for row in rows]

    async def asignar_contacto_principal(
        self,
        *,
        id_evento_empresa: int,
        id_contacto: int,
        actor: Usuario,
        id_programacion_evento: int | None = None,
    ) -> EventoEmpresaResponse:
        evento_empresa = await self.participantes.get_evento_empresa_by_id(
            id_evento_empresa, id_programacion_evento=id_programacion_evento
        )
        if evento_empresa is None:
            raise EventoEmpresaNotFoundError("Afiliación no encontrada.")
        await self._get_open_programacion(evento_empresa.id_programacion_evento)
        contacto = await self.participantes.get_contacto(id_contacto)
        if contacto is None or contacto.id_empresa != evento_empresa.id_empresa:
            raise ContactoPrincipalInvalidoError(
                "El contacto debe pertenecer a la empresa afiliada."
            )
        if not contacto.estado:
            raise ContactoInactiveError("El contacto se encuentra inactivo.")

        contacto_anterior = evento_empresa.id_contacto_principal
        anterior = {"id_contacto_principal": contacto_anterior}
        try:
            if contacto_anterior is not None and contacto_anterior != id_contacto:
                # El contacto principal cambió: el código enviado a la persona
                # anterior ya no debe servir.
                await self.participantes.invalidar_codigos(id_evento_empresa)
            await self.participantes.set_contacto_principal(
                evento_empresa, id_contacto=id_contacto
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento_empresa",
                id_entidad=evento_empresa.id_evento_empresa,
                accion="ASIGNAR_CONTACTO_PRINCIPAL",
                valor_anterior=anterior,
                valor_nuevo={"id_contacto_principal": id_contacto},
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return await self._get_evento_empresa_response(
            id_evento_empresa,
            id_programacion_evento=evento_empresa.id_programacion_evento,
        )

    async def enviar_codigo_acceso(
        self,
        *,
        id_evento_empresa: int,
        actor: Usuario,
        motivo: str | None = None,
        id_programacion_evento: int | None = None,
    ) -> EventoEmpresaResponse:
        evento_empresa = await self.participantes.get_evento_empresa_by_id(
            id_evento_empresa, id_programacion_evento=id_programacion_evento
        )
        if evento_empresa is None:
            raise EventoEmpresaNotFoundError("Afiliación no encontrada.")
        await self._get_open_programacion(evento_empresa.id_programacion_evento)
        if evento_empresa.id_contacto_principal is None:
            raise ContactoPrincipalInvalidoError(
                "Debe asignar un contacto principal antes de enviar el código."
            )
        contacto = await self.participantes.get_contacto(
            evento_empresa.id_contacto_principal
        )
        if contacto is None or not contacto.correo:
            raise ContactoPrincipalInvalidoError(
                "El contacto principal no tiene un correo registrado."
            )
        dias = await self.eventos.list_dias(evento_empresa.id_programacion_evento)
        if not dias:
            raise ProgramacionSinDiasError(
                "La programación debe tener al menos un día registrado."
            )
        primer_dia = min(dias, key=lambda dia: dia.fecha)
        expira_en = self._expiracion_codigo_acceso(primer_dia)
        # El portal rechaza un código vencido, así que enviarlo solo generaría
        # un correo inservible: se avisa antes en vez de fallar del otro lado.
        if expira_en <= datetime.now(timezone.utc):
            raise CodigoAccesoYaVencidoError(
                "El primer día de la programación ya terminó, por lo que el "
                "código de acceso nacería vencido. Actualice las fechas de la "
                "programación antes de enviarlo."
            )

        empresa = await self.participantes.get_empresa(evento_empresa.id_empresa)
        assert empresa is not None
        programacion = await self.participantes.get_programacion(
            evento_empresa.id_programacion_evento
        )
        assert programacion is not None
        evento = await self.eventos.get_by_id(programacion.id_evento)
        codigo_plano = generate_portal_code()
        try:
            await self.participantes.invalidar_codigos(id_evento_empresa)
            codigo = await self.participantes.create_codigo(
                id_evento_empresa=id_evento_empresa,
                codigo_hash=hash_portal_code(codigo_plano),
                expira_en=expira_en,
            )
            await self.correo.notify_codigo_acceso(
                CodigoAccesoEmail(
                    sender_email=SENDER_DESDE_CONFIGURACION,
                    recipient_email=contacto.correo,
                    recipient_name=contacto.nombre_completo,
                    nombre_empresa=empresa.nombre_empresa,
                    nombre_evento=(
                        evento.nombre_evento if evento is not None else ""
                    ),
                    fecha_evento=self._formato_fecha_evento(primer_dia),
                    codigo=codigo_plano,
                    expira_en=self._formato_expiracion(expira_en),
                    portal_url=(
                        f"{settings.frontend_base_url}/portal-invitados"
                        f"?codigo={codigo_plano}"
                    ),
                )
            )
            await self.participantes.mark_codigo_enviado(codigo)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="codigo_acceso_principal",
                id_entidad=codigo.id_codigo_acceso_principal,
                accion="ENVIAR_CODIGO_ACCESO",
                motivo=motivo,
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return await self._get_evento_empresa_response(
            id_evento_empresa,
            id_programacion_evento=evento_empresa.id_programacion_evento,
        )

    async def enviar_codigo_acceso_masivo(
        self, *, id_programacion_evento: int, actor: Usuario
    ) -> EnviarCodigoAccesoMasivoResponse:
        await self._get_open_programacion(id_programacion_evento)
        ids = await self.participantes.list_ids_evento_empresa(
            id_programacion_evento
        )
        enviados = 0
        omitidos = 0
        ya_enviados = 0
        for id_evento_empresa in ids:
            if await self._tiene_codigo_vigente_enviado(id_evento_empresa):
                ya_enviados += 1
                continue
            try:
                await self.enviar_codigo_acceso(
                    id_evento_empresa=id_evento_empresa,
                    actor=actor,
                    id_programacion_evento=id_programacion_evento,
                )
                enviados += 1
            except (ParticipanteServiceError, EmailDeliveryError):
                omitidos += 1
        return EnviarCodigoAccesoMasivoResponse(
            enviados=enviados, omitidos=omitidos, ya_enviados=ya_enviados
        )

    async def _tiene_codigo_vigente_enviado(self, id_evento_empresa: int) -> bool:
        codigo = await self.participantes.get_codigo_vigente(id_evento_empresa)
        if codigo is None or codigo.fecha_envio is None:
            return False
        return codigo.expira_en > datetime.now(timezone.utc)

    # -- EventoContacto ------------------------------------------------

    async def agregar_evento_contactos(
        self,
        *,
        id_programacion_evento: int,
        data: EventoContactoCreateMultiple,
        actor: Usuario | None,
    ) -> EventoContactoCreateResponse:
        await self._get_open_programacion(id_programacion_evento)
        contactos = await self.participantes.get_contactos(data.ids_contacto)
        contactos_por_id = {contacto.id_contacto: contacto for contacto in contactos}

        missing = [
            id_contacto
            for id_contacto in data.ids_contacto
            if id_contacto not in contactos_por_id
        ]
        if missing:
            raise ContactoNotFoundError(
                f"No se encontraron los contactos: {', '.join(map(str, missing))}."
            )
        for contacto in contactos:
            if not contacto.estado:
                raise ContactoInactiveError(
                    f"El contacto {contacto.id_contacto} se encuentra inactivo."
                )
            await self._validar_empresa_afiliada(
                id_programacion_evento=id_programacion_evento,
                id_empresa=contacto.id_empresa,
            )

        await self.validar_evento_contactos_no_duplicados(
            id_programacion_evento=id_programacion_evento,
            ids_contacto=data.ids_contacto,
        )

        created_ids: list[int] = []
        try:
            for id_contacto in data.ids_contacto:
                evento_contacto = await self.participantes.create_evento_contacto(
                    id_programacion_evento=id_programacion_evento,
                    id_contacto=id_contacto,
                    id_empresa=contactos_por_id[id_contacto].id_empresa,
                )
                await self._generar_qr(evento_contacto.id_evento_contacto)
                created_ids.append(evento_contacto.id_evento_contacto)
                await self.auditoria.create(
                    id_usuario=actor.id_usuario if actor else None,
                    id_modulo=await self._id_modulo(),
                    entidad="evento_contacto",
                    id_entidad=evento_contacto.id_evento_contacto,
                    accion="AGREGAR_EVENTO_CONTACTO",
                    valor_nuevo=self._evento_contacto_values(evento_contacto),
                )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise DuplicateEventoContactoError(
                "Uno de los contactos ya participa en esta programación."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

        responses = [
            await self.obtener_evento_contacto(id_evento_contacto)
            for id_evento_contacto in created_ids
        ]
        return EventoContactoCreateResponse(
            created=len(responses), evento_contactos=responses
        )

    async def crear_contacto_y_evento_contacto(
        self,
        *,
        id_programacion_evento: int,
        data: ContactoDesdeEventoCreate,
        actor: Usuario,
    ) -> EventoContactoResponse:
        await self._get_open_programacion(id_programacion_evento)
        await self._validar_empresa_afiliada(
            id_programacion_evento=id_programacion_evento,
            id_empresa=data.contacto.id_empresa,
        )

        try:
            contacto = await self.contactos.crear_contacto(
                data=data.contacto,
                actor=actor,
                commit=False,
            )
            evento_contacto = await self.participantes.create_evento_contacto(
                id_programacion_evento=id_programacion_evento,
                id_contacto=contacto.id_contacto,
                id_empresa=contacto.id_empresa,
            )
            await self._generar_qr(evento_contacto.id_evento_contacto)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento_contacto",
                id_entidad=evento_contacto.id_evento_contacto,
                accion="CREAR_CONTACTO_DESDE_EVENTO",
                valor_nuevo={
                    **self._evento_contacto_values(evento_contacto),
                    "contacto_creado": contacto.id_contacto,
                },
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ParticipantePersistenceConflictError(
                "No se pudo crear el contacto y su participación por un conflicto de datos."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

        return await self.obtener_evento_contacto(evento_contacto.id_evento_contacto)

    async def obtener_evento_contacto(
        self, id_evento_contacto: int
    ) -> EventoContactoResponse:
        detalle = await self.participantes.get_evento_contacto_detalle(
            id_evento_contacto
        )
        if detalle is None:
            raise EventoContactoNotFoundError("Participación no encontrada.")
        return self._evento_contacto_response(detalle)

    async def listar_evento_contactos(
        self,
        *,
        id_programacion_evento: int | None,
        id_empresa: int | None,
        id_contacto: int | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> EventoContactoListResponse:
        rows, total = await self.participantes.list_evento_contactos(
            id_programacion_evento=id_programacion_evento,
            id_empresa=id_empresa,
            id_contacto=id_contacto,
            search=search,
            page=page,
            page_size=page_size,
        )
        return EventoContactoListResponse(
            items=[self._evento_contacto_response(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def marcar_asistencia(
        self, *, id_evento_contacto: int, actor: Usuario
    ) -> EventoContactoResponse:
        evento_contacto = await self._get_evento_contacto_for_update(
            id_evento_contacto
        )
        await self._get_open_programacion(evento_contacto.id_programacion_evento)
        anterior = self._evento_contacto_values(evento_contacto)
        try:
            await self.participantes.update_evento_contacto(
                evento_contacto,
                {
                    "asistencia_evento": True,
                    "hora_ingreso": datetime.now(timezone.utc),
                },
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento_contacto",
                id_entidad=id_evento_contacto,
                accion="MARCAR_ASISTENCIA_EVENTO_CONTACTO",
                valor_anterior=anterior,
                valor_nuevo=self._evento_contacto_values(evento_contacto),
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return await self.obtener_evento_contacto(id_evento_contacto)

    async def validar_evento_contactos_no_duplicados(
        self, *, id_programacion_evento: int, ids_contacto: list[int]
    ) -> None:
        existing = await self.participantes.get_existing_contact_ids(
            id_programacion_evento=id_programacion_evento,
            ids_contacto=ids_contacto,
        )
        if existing:
            raise DuplicateEventoContactoError(
                "Los siguientes contactos ya participan en esta programación: "
                f"{', '.join(map(str, sorted(existing)))}."
            )

    async def agregar_invitado_sin_registrar(
        self,
        *,
        id_programacion_evento: int,
        id_empresa: int,
        data: InvitadoCreate,
        actor: Usuario | None,
    ) -> EventoContactoResponse:
        await self._get_open_programacion(id_programacion_evento)
        await self._validar_empresa_afiliada(
            id_programacion_evento=id_programacion_evento, id_empresa=id_empresa
        )
        actuales = await self.participantes.count_invitados_sin_registrar(
            id_programacion_evento=id_programacion_evento, id_empresa=id_empresa
        )
        if actuales >= LIMITE_INVITADOS_SIN_REGISTRAR:
            raise LimiteInvitadosSuperadoError(
                f"Se alcanzó el límite de {LIMITE_INVITADOS_SIN_REGISTRAR} "
                "invitados no registrados para esta empresa."
            )

        correo = str(data.correo)
        duplicado_en_programacion = (
            await self.participantes.get_invitado_duplicado_en_programacion(
                id_programacion_evento=id_programacion_evento,
                numero_documento=data.numero_documento,
                correo=correo,
            )
        )
        if duplicado_en_programacion is not None:
            raise InvitadoDuplicadoEnProgramacionError(
                "Ya se registró un invitado con ese número de documento o "
                "correo en esta programación."
            )
        contacto_existente = await self.contactos.contactos.get_by_documento(
            data.numero_documento
        )
        if contacto_existente is None:
            contacto_existente = await self.contactos.contactos.get_by_correo(correo)
        if contacto_existente is not None:
            raise InvitadoDatosConflictoError(
                "No se pudo registrar al invitado con los datos indicados. "
                "Comuníquese con CODIP para verificar y agregar al contacto."
            )

        if data.id_beneficio is not None:
            beneficio = await self.maestros.get_beneficio_by_id(data.id_beneficio)
            if beneficio is None or not beneficio.estado:
                raise ParticipanteBeneficioNotFoundError("Beneficio no encontrado.")

        try:
            evento_contacto = (
                await self.participantes.create_evento_contacto_invitado(
                    id_programacion_evento=id_programacion_evento,
                    id_empresa=id_empresa,
                    nombres=data.nombres.strip(),
                    apellidos=data.apellidos.strip(),
                    numero_documento=data.numero_documento,
                    correo=correo,
                    celular=data.celular,
                )
            )
            await self._generar_qr(evento_contacto.id_evento_contacto)
            await self.auditoria.create(
                id_usuario=actor.id_usuario if actor else None,
                id_modulo=await self._id_modulo(),
                entidad="evento_contacto",
                id_entidad=evento_contacto.id_evento_contacto,
                accion="AGREGAR_INVITADO_SIN_REGISTRAR",
                valor_nuevo=self._evento_contacto_values(evento_contacto),
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

        if data.id_beneficio is not None:
            await self.asignar_beneficio(
                data=AsignarBeneficioRequest(
                    ids_evento_contacto=[evento_contacto.id_evento_contacto],
                    id_beneficio=data.id_beneficio,
                ),
                actor=actor,
            )
        return await self.obtener_evento_contacto(evento_contacto.id_evento_contacto)

    async def actualizar_estado_evento_contacto(
        self, *, id_evento_contacto: int, estado: bool, actor: Usuario
    ) -> EventoContactoResponse:
        evento_contacto = await self._get_evento_contacto_for_update(
            id_evento_contacto
        )
        await self._get_open_programacion(evento_contacto.id_programacion_evento)
        anterior = self._evento_contacto_values(evento_contacto)
        try:
            await self.participantes.update_evento_contacto(
                evento_contacto, {"estado": estado}
            )
            if not estado:
                qr = await self.participantes.get_participante_qr_by_evento_contacto(
                    id_evento_contacto
                )
                if qr is not None:
                    qr.estado = False
                    await self.db.flush()
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento_contacto",
                id_entidad=id_evento_contacto,
                accion="ACTIVAR_EVENTO_CONTACTO" if estado else "DESACTIVAR_EVENTO_CONTACTO",
                valor_anterior=anterior,
                valor_nuevo=self._evento_contacto_values(evento_contacto),
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return await self.obtener_evento_contacto(id_evento_contacto)

    async def eliminar_invitado(
        self, *, id_evento_contacto: int, motivo: str | None, actor: Usuario
    ) -> None:
        evento_contacto = await self._get_evento_contacto_for_update(
            id_evento_contacto
        )
        await self._get_open_programacion(evento_contacto.id_programacion_evento)
        if evento_contacto.id_contacto is not None:
            raise InvitadoInvalidoError(
                "Solo se pueden eliminar invitados sin registrar; los "
                "contactos registrados deben desactivarse."
            )

        anterior = self._evento_contacto_values(evento_contacto)
        try:
            await self.participantes.delete_evento_contacto(evento_contacto)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento_contacto",
                id_entidad=id_evento_contacto,
                accion="ELIMINAR_INVITADO",
                valor_anterior=anterior,
                motivo=motivo,
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

    # -- AsignacionBeneficio -------------------------------------------

    async def asignar_beneficio(
        self, *, data: AsignarBeneficioRequest, actor: Usuario | None
    ) -> list[EventoContactoResponse]:
        beneficio = await self.maestros.get_beneficio_by_id(data.id_beneficio)
        if beneficio is None or not beneficio.estado:
            raise ParticipanteBeneficioNotFoundError("Beneficio no encontrado.")
        if len(data.ids_evento_contacto) != beneficio.personas_por_asignacion:
            raise AsignacionBeneficioCantidadInvalidaError(
                f"Este beneficio requiere exactamente "
                f"{beneficio.personas_por_asignacion} contacto(s) por asignación."
            )

        detalles = [
            await self._get_evento_contacto_detalle_for_update(id_evento_contacto)
            for id_evento_contacto in data.ids_evento_contacto
        ]
        primero = detalles[0]
        id_programacion_evento = primero.evento_contacto.id_programacion_evento
        id_empresa = primero.empresa.id_empresa
        await self._get_open_programacion(id_programacion_evento)
        for detalle in detalles[1:]:
            if (
                detalle.evento_contacto.id_programacion_evento
                != id_programacion_evento
                or detalle.empresa.id_empresa != id_empresa
            ):
                raise AsignacionBeneficioGrupoInvalidoError(
                    "Todos los contactos de una misma asignación deben "
                    "pertenecer a la misma empresa y programación."
                )
        for detalle in detalles:
            if (
                await self.participantes.get_asignacion_beneficio(
                    detalle.evento_contacto.id_evento_contacto
                )
                is not None
            ):
                raise AsignacionBeneficioExistenteError(
                    f"El contacto {detalle.evento_contacto.id_evento_contacto} ya "
                    "tiene un beneficio asignado; retírelo antes de reasignar."
                )

        if beneficio.tipo_calculo != TipoCalculoBeneficio.SIN_BENEFICIO:
            await self._validar_cupo_beneficio(
                beneficio=beneficio,
                id_programacion_evento=id_programacion_evento,
                id_empresa=id_empresa,
                id_categoria=primero.categoria.id_categoria,
                cantidad_solicitada=len(data.ids_evento_contacto),
            )

        codigo_grupo = uuid4().hex if len(data.ids_evento_contacto) > 1 else None
        try:
            for detalle in detalles:
                asignacion = await self.participantes.create_asignacion_beneficio(
                    id_evento_contacto=detalle.evento_contacto.id_evento_contacto,
                    id_beneficio=beneficio.id_beneficio,
                    codigo_grupo=codigo_grupo,
                )
                await self.participantes.update_evento_contacto(
                    detalle.evento_contacto,
                    {
                        "requiere_coordinacion": (
                            beneficio.tipo_calculo == TipoCalculoBeneficio.SIN_BENEFICIO
                        )
                    },
                )
                await self.auditoria.create(
                    id_usuario=actor.id_usuario if actor else None,
                    id_modulo=await self._id_modulo(),
                    entidad="asignacion_beneficio",
                    id_entidad=asignacion.id_asignacion_beneficio,
                    accion="ASIGNAR_BENEFICIO",
                    valor_nuevo={
                        "id_evento_contacto": detalle.evento_contacto.id_evento_contacto,
                        "id_beneficio": beneficio.id_beneficio,
                        "codigo_grupo": codigo_grupo,
                    },
                )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise AsignacionBeneficioExistenteError(
                "Uno de los contactos ya tiene un beneficio asignado."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

        return [
            await self.obtener_evento_contacto(
                detalle.evento_contacto.id_evento_contacto
            )
            for detalle in detalles
        ]

    async def remover_asignacion_beneficio(
        self, *, id_evento_contacto: int, actor: Usuario
    ) -> EventoContactoResponse:
        asignacion = await self.participantes.get_asignacion_beneficio(
            id_evento_contacto
        )
        if asignacion is None:
            raise AsignacionBeneficioNotFoundError(
                "Este contacto no tiene un beneficio asignado."
            )
        evento_contacto = await self._get_evento_contacto_for_update(
            id_evento_contacto
        )
        await self._get_open_programacion(evento_contacto.id_programacion_evento)
        try:
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="asignacion_beneficio",
                id_entidad=asignacion.id_asignacion_beneficio,
                accion="REMOVER_ASIGNACION_BENEFICIO",
                valor_anterior={
                    "id_evento_contacto": id_evento_contacto,
                    "id_beneficio": asignacion.id_beneficio,
                    "codigo_grupo": asignacion.codigo_grupo,
                },
            )
            await self.participantes.delete_asignacion_beneficio(asignacion)
            await self.participantes.update_evento_contacto(
                evento_contacto, {"requiere_coordinacion": True}
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return await self.obtener_evento_contacto(id_evento_contacto)

    async def listar_beneficios_disponibles(
        self, id_evento_contacto: int
    ) -> list[BeneficioDisponibleResponse]:
        detalle = await self._get_evento_contacto_detalle(id_evento_contacto)
        programacion = await self.participantes.get_programacion(
            detalle.evento_contacto.id_programacion_evento
        )
        assert programacion is not None
        return await self.beneficios_disponibles_para(
            id_programacion_evento=detalle.evento_contacto.id_programacion_evento,
            id_evento=programacion.id_evento,
            id_empresa=detalle.empresa.id_empresa,
            id_categoria=detalle.categoria.id_categoria,
        )

    async def beneficios_disponibles_para(
        self,
        *,
        id_programacion_evento: int,
        id_evento: int,
        id_empresa: int,
        id_categoria: int,
    ) -> list[BeneficioDisponibleResponse]:
        evento_detalle = await self.eventos.get_detallado(id_evento)
        assert evento_detalle is not None
        beneficios_todos, _ = await self.maestros.list_beneficios(
            search=None, estado=True, page=1, page_size=1000
        )
        resultados: list[BeneficioDisponibleResponse] = []
        for beneficio in beneficios_todos:
            if beneficio.tipo_calculo == TipoCalculoBeneficio.SIN_BENEFICIO:
                # No se ofrece como opción seleccionable: no asignar ningún
                # beneficio ya logra el mismo efecto (marca requiere_coordinacion
                # automáticamente al crear el participante o al remover un beneficio).
                continue
            match = next(
                (
                    par
                    for par in evento_detalle.detalles
                    if par[1].id_beneficio == beneficio.id_beneficio
                    and par[2].id_categoria == id_categoria
                ),
                None,
            )
            if match is None:
                continue
            detalle_politica = match[0]
            cupo_restante = await self._cupo_restante(
                beneficio=beneficio,
                id_programacion_evento=id_programacion_evento,
                id_evento=id_evento,
                id_empresa=id_empresa,
                entradas_gratuitas=detalle_politica.entradas_gratuitas,
                politica_fecha_inicio=evento_detalle.politica.fecha_inicio,
                politica_fecha_fin=evento_detalle.politica.fecha_fin,
            )
            resultados.append(
                BeneficioDisponibleResponse(
                    id_beneficio=beneficio.id_beneficio,
                    nombre=beneficio.nombre,
                    tipo_calculo=beneficio.tipo_calculo,
                    personas_por_asignacion=beneficio.personas_por_asignacion,
                    disponible=cupo_restante >= beneficio.personas_por_asignacion,
                    cupo_restante=cupo_restante,
                )
            )
        return resultados

    # -- QR de ingreso ---------------------------------------------------

    async def enviar_qr(
        self, *, id_evento_contacto: int, actor: Usuario
    ) -> EventoContactoResponse:
        detalle = await self._get_evento_contacto_detalle(id_evento_contacto)
        await self._get_open_programacion(detalle.evento_contacto.id_programacion_evento)
        nombre_completo, _, correo, _, _ = self._participante_datos(detalle)
        if not correo:
            raise ParticipanteQrNotFoundError(
                "El contacto no tiene un correo registrado."
            )
        qr = await self.participantes.get_participante_qr_by_evento_contacto(
            id_evento_contacto
        )
        if qr is None:
            qr = await self._generar_qr(id_evento_contacto)
        try:
            await self.correo.notify_participante_qr(
                ParticipanteQrEmail(
                    sender_email=SENDER_DESDE_CONFIGURACION,
                    recipient_email=correo,
                    recipient_name=nombre_completo,
                    codigo_seguro=qr.codigo_seguro,
                )
            )
            await self.participantes.mark_qr_enviado(qr)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="participante_qr",
                id_entidad=qr.id_participante_qr,
                accion="ENVIAR_QR",
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return await self.obtener_evento_contacto(id_evento_contacto)

    async def enviar_qr_masivo(
        self, *, id_programacion_evento: int, actor: Usuario
    ) -> EnviarQrMasivoResponse:
        await self._get_open_programacion(id_programacion_evento)
        ids = await self.participantes.list_ids_evento_contacto(
            id_programacion_evento
        )
        enviados = 0
        omitidos = 0
        for id_evento_contacto in ids:
            try:
                await self.enviar_qr(
                    id_evento_contacto=id_evento_contacto, actor=actor
                )
                enviados += 1
            except (ParticipanteServiceError, EmailDeliveryError):
                omitidos += 1
        return EnviarQrMasivoResponse(enviados=enviados, omitidos=omitidos)

    async def escanear_qr(self, codigo_seguro: str) -> EscaneoQrResponse:
        qr = await self.participantes.get_participante_qr_by_codigo(codigo_seguro)
        if qr is None:
            raise ParticipanteQrNotFoundError("Código QR no encontrado o inválido.")
        detalle = await self._get_evento_contacto_detalle(qr.id_evento_contacto)
        return self._escaneo_response(detalle)

    async def imprimir_credencial(
        self, *, codigo_seguro: str, actor: Usuario
    ) -> EscaneoQrResponse:
        qr = await self.participantes.get_participante_qr_by_codigo(codigo_seguro)
        if qr is None:
            raise ParticipanteQrNotFoundError("Código QR no encontrado o inválido.")
        evento_contacto = await self._get_evento_contacto_for_update(
            qr.id_evento_contacto
        )
        await self._get_open_programacion(evento_contacto.id_programacion_evento)
        if evento_contacto.credencial_impresa:
            raise CredencialYaImpresaError(
                "La credencial ya fue impresa; use la opción de reimpresión."
            )
        anterior = self._evento_contacto_values(evento_contacto)
        try:
            await self.participantes.update_evento_contacto(
                evento_contacto,
                {
                    "asistencia_evento": True,
                    "hora_ingreso": datetime.now(timezone.utc),
                    "credencial_impresa": True,
                },
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento_contacto",
                id_entidad=evento_contacto.id_evento_contacto,
                accion="IMPRIMIR_CREDENCIAL",
                valor_anterior=anterior,
                valor_nuevo=self._evento_contacto_values(evento_contacto),
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        detalle = await self._get_evento_contacto_detalle(
            evento_contacto.id_evento_contacto
        )
        return self._escaneo_response(detalle)

    async def reimprimir_credencial(
        self, *, id_evento_contacto: int, data: ReimprimirCredencialRequest
    ) -> EscaneoQrResponse:
        evento_contacto = await self._get_evento_contacto_for_update(
            id_evento_contacto
        )
        await self._get_open_programacion(evento_contacto.id_programacion_evento)
        responsable = await self.eventos.get_responsable_by_id(
            id_programacion_evento=evento_contacto.id_programacion_evento,
            id_responsable=data.id_responsable_evento,
        )
        if responsable is None or not responsable.estado:
            raise ResponsableInvalidoError(
                "El responsable no pertenece a esta programación o está inactivo."
            )
        usuario_responsable = await self.usuarios.get_by_id(responsable.id_usuario)
        if usuario_responsable is None or not verify_password(
            data.password, usuario_responsable.password_hash
        ):
            raise PasswordIncorrectoError("Contraseña incorrecta.")

        try:
            await self.auditoria.create(
                id_usuario=usuario_responsable.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento_contacto",
                id_entidad=id_evento_contacto,
                accion="REIMPRESION_CREDENCIAL",
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        detalle = await self._get_evento_contacto_detalle(id_evento_contacto)
        return self._escaneo_response(detalle)

    # -- helpers -----------------------------------------------------

    async def _get_open_programacion(
        self, id_programacion_evento: int
    ) -> ProgramacionEvento:
        programacion = await self.participantes.get_programacion(
            id_programacion_evento, for_update=True
        )
        if programacion is None:
            raise ProgramacionNotFoundError("Programación no encontrada.")
        evento = await self.participantes.get_evento_by_programacion_for_update(
            id_programacion_evento
        )
        assert evento is not None
        try:
            EventoService.validar_evento_abierto(evento)
        except EventoNotEditableError as exc:
            raise EventoNotOpenError(
                "El evento debe estar ABIERTO para ejecutar esta operación."
            ) from exc
        try:
            EventoService.validar_programacion_abierta(programacion)
        except ProgramacionNotEditableError as exc:
            raise EventoNotOpenError(
                "La programación debe estar ABIERTA para ejecutar esta operación."
            ) from exc
        return programacion

    async def _get_active_company(self, id_empresa: int) -> Empresa:
        empresa = await self.participantes.get_empresa(id_empresa)
        if empresa is None:
            raise EmpresaNotFoundError("Empresa no encontrada.")
        if not empresa.estado:
            raise EmpresaInactiveError("La empresa se encuentra inactiva.")
        return empresa

    async def _validar_empresa_afiliada(
        self, *, id_programacion_evento: int, id_empresa: int
    ) -> None:
        await self._get_active_company(id_empresa)
        if (
            await self.participantes.get_evento_empresa_activa(
                id_programacion_evento=id_programacion_evento, id_empresa=id_empresa
            )
            is None
        ):
            raise ContactoSinEmpresaAfiliadaError(
                "La empresa del contacto no está afiliada activamente a esta "
                "programación."
            )

    async def _get_evento_contacto_for_update(
        self, id_evento_contacto: int
    ) -> EventoContacto:
        evento_contacto = await self.participantes.get_evento_contacto_by_id(
            id_evento_contacto, for_update=True
        )
        if evento_contacto is None:
            raise EventoContactoNotFoundError("Participación no encontrada.")
        return evento_contacto

    async def _get_evento_contacto_detalle(
        self, id_evento_contacto: int
    ) -> EventoContactoDetalle:
        detalle = await self.participantes.get_evento_contacto_detalle(
            id_evento_contacto
        )
        if detalle is None:
            raise EventoContactoNotFoundError("Participación no encontrada.")
        return detalle

    async def _get_evento_contacto_detalle_for_update(
        self, id_evento_contacto: int
    ) -> EventoContactoDetalle:
        await self._get_evento_contacto_for_update(id_evento_contacto)
        return await self._get_evento_contacto_detalle(id_evento_contacto)

    async def _validar_cupo_beneficio(
        self,
        *,
        beneficio: Beneficio,
        id_programacion_evento: int,
        id_empresa: int,
        id_categoria: int,
        cantidad_solicitada: int,
    ) -> None:
        programacion = await self.participantes.get_programacion(
            id_programacion_evento
        )
        assert programacion is not None
        evento_detalle = await self.eventos.get_detallado(programacion.id_evento)
        assert evento_detalle is not None
        match = next(
            (
                par
                for par in evento_detalle.detalles
                if par[1].id_beneficio == beneficio.id_beneficio
                and par[2].id_categoria == id_categoria
            ),
            None,
        )
        if match is None:
            raise BeneficioNoAplicableError(
                "Este beneficio no aplica a la categoría de la empresa según la "
                "política del evento."
            )
        detalle_politica = match[0]
        if beneficio.tipo_calculo == TipoCalculoBeneficio.POR_EVENTO:
            filas = await self.participantes.list_asignaciones_por_evento(
                id_programacion_evento=id_programacion_evento,
                id_empresa=id_empresa,
                id_beneficio=beneficio.id_beneficio,
            )
        else:
            filas = await self.participantes.list_asignaciones_por_anio(
                id_evento=programacion.id_evento,
                id_empresa=id_empresa,
                id_beneficio=beneficio.id_beneficio,
                fecha_inicio=evento_detalle.politica.fecha_inicio,
                fecha_fin=evento_detalle.politica.fecha_fin,
            )
        if not hay_cupo_disponible(
            tipo_calculo=beneficio.tipo_calculo,
            entradas_gratuitas=detalle_politica.entradas_gratuitas,
            personas_por_asignacion=beneficio.personas_por_asignacion,
            filas_existentes=filas,
            cantidad_solicitada=cantidad_solicitada,
        ):
            raise CupoBeneficioAgotadoError(
                "No hay cupo disponible para este beneficio."
            )

    async def _cupo_restante(
        self,
        *,
        beneficio: Beneficio,
        id_programacion_evento: int,
        id_evento: int,
        id_empresa: int,
        entradas_gratuitas: int,
        politica_fecha_inicio: Any,
        politica_fecha_fin: Any,
    ) -> int:
        if beneficio.tipo_calculo == TipoCalculoBeneficio.POR_EVENTO:
            filas = await self.participantes.list_asignaciones_por_evento(
                id_programacion_evento=id_programacion_evento,
                id_empresa=id_empresa,
                id_beneficio=beneficio.id_beneficio,
            )
        else:
            filas = await self.participantes.list_asignaciones_por_anio(
                id_evento=id_evento,
                id_empresa=id_empresa,
                id_beneficio=beneficio.id_beneficio,
                fecha_inicio=politica_fecha_inicio,
                fecha_fin=politica_fecha_fin,
            )
        restante = calcular_cupo_restante(
            tipo_calculo=beneficio.tipo_calculo,
            entradas_gratuitas=entradas_gratuitas,
            personas_por_asignacion=beneficio.personas_por_asignacion,
            filas_existentes=filas,
        )
        assert restante is not None
        return restante

    async def _generar_qr(self, id_evento_contacto: int) -> ParticipanteQr:
        codigo_seguro = secrets.token_urlsafe(32)
        existente = await self.participantes.get_participante_qr_by_evento_contacto(
            id_evento_contacto, solo_activos=False
        )
        if existente is not None:
            return await self.participantes.reactivar_participante_qr(
                existente, codigo_seguro=codigo_seguro
            )
        return await self.participantes.create_participante_qr(
            id_evento_contacto=id_evento_contacto, codigo_seguro=codigo_seguro
        )

    @staticmethod
    def _formato_fecha_evento(primer_dia: Any) -> str:
        fecha = primer_dia.fecha.strftime("%d/%m/%Y")
        if primer_dia.hora_inicio is None:
            return fecha
        inicio = primer_dia.hora_inicio.strftime("%H:%M")
        if primer_dia.hora_fin is None:
            return f"{fecha} desde las {inicio}"
        return f"{fecha} de {inicio} a {primer_dia.hora_fin.strftime('%H:%M')}"

    @staticmethod
    def _formato_expiracion(expira_en: datetime) -> str:
        local = expira_en.astimezone(PERU_TIMEZONE)
        return local.strftime("%d/%m/%Y a las %H:%M")

    @staticmethod
    def _expiracion_codigo_acceso(primer_dia: Any) -> datetime:
        """Vence al terminar el primer día del evento, en hora de Perú.

        El portal sirve para que la empresa inscriba participantes, así que el
        código debe seguir vigente hasta que ese día acabe. Atarlo a una fecha
        anterior dejaba sin portal a los eventos creados para hoy o mañana.
        """
        fin_del_dia = primer_dia.hora_fin or time.max
        return datetime.combine(
            primer_dia.fecha, fin_del_dia, tzinfo=PERU_TIMEZONE
        ).astimezone(timezone.utc)

    @staticmethod
    def _participante_datos(
        detalle: EventoContactoDetalle,
    ) -> tuple[str, str | None, str | None, str | None, str | None]:
        evento_contacto = detalle.evento_contacto
        if detalle.contacto is not None:
            contacto = detalle.contacto
            return (
                contacto.nombre_completo,
                contacto.numero_documento,
                contacto.correo,
                contacto.celular,
                contacto.alias,
            )
        nombre_completo = (
            f"{evento_contacto.invitado_nombres} {evento_contacto.invitado_apellidos}"
        ).strip()
        return (
            nombre_completo,
            evento_contacto.invitado_numero_documento,
            evento_contacto.invitado_correo,
            evento_contacto.invitado_celular,
            None,
        )

    @staticmethod
    def _escaneo_response(detalle: EventoContactoDetalle) -> EscaneoQrResponse:
        evento_contacto = detalle.evento_contacto
        nombre_completo, numero_documento, _, _, alias = (
            ParticipanteService._participante_datos(detalle)
        )
        return EscaneoQrResponse(
            id_evento_contacto=evento_contacto.id_evento_contacto,
            nombre_completo=nombre_completo,
            alias=alias,
            numero_documento=numero_documento,
            nombre_empresa=detalle.empresa.nombre_empresa,
            id_beneficio_asignado=detalle.id_beneficio_asignado,
            nombre_beneficio_asignado=detalle.nombre_beneficio_asignado,
            asistencia_evento=evento_contacto.asistencia_evento,
            hora_ingreso=evento_contacto.hora_ingreso,
            credencial_impresa=evento_contacto.credencial_impresa,
        )

    async def _get_evento_empresa_response(
        self,
        id_evento_empresa: int,
        *,
        id_programacion_evento: int | None = None,
    ) -> EventoEmpresaResponse:
        detalle = await self.participantes.get_evento_empresa_detalle(
            id_evento_empresa,
            id_programacion_evento=id_programacion_evento,
        )
        if detalle is None:
            raise EventoEmpresaNotFoundError("Afiliación no encontrada.")
        return self._evento_empresa_response(detalle)

    async def _id_modulo(self) -> int | None:
        modulo = await self.usuarios.get_module_by_name(MODULO_PARTICIPANTES)
        return modulo.id_modulo if modulo else None

    @staticmethod
    def _evento_empresa_response(
        detalle: EventoEmpresaDetalle,
    ) -> EventoEmpresaResponse:
        relation = detalle.evento_empresa
        return EventoEmpresaResponse(
            id_evento_empresa=relation.id_evento_empresa,
            id_programacion_evento=detalle.id_programacion_evento,
            id_empresa=relation.id_empresa,
            nombre_empresa=detalle.empresa.nombre_empresa,
            ruc=detalle.empresa.ruc,
            id_grupo=detalle.grupo.id_grupo,
            nombre_grupo=detalle.grupo.nombre_grupo,
            id_categoria=detalle.categoria.id_categoria,
            nombre_categoria=detalle.categoria.nombre_categoria,
            id_contacto_principal=(
                detalle.contacto_principal.id_contacto
                if detalle.contacto_principal
                else None
            ),
            nombre_contacto_principal=(
                detalle.contacto_principal.nombre_completo
                if detalle.contacto_principal
                else None
            ),
            codigo_enviado_en=detalle.codigo_fecha_envio,
            estado=relation.estado,
        )

    @staticmethod
    def _evento_contacto_response(
        detalle: EventoContactoDetalle,
    ) -> EventoContactoResponse:
        evento_contacto = detalle.evento_contacto
        nombre_completo, numero_documento, correo, celular, _ = (
            ParticipanteService._participante_datos(detalle)
        )
        return EventoContactoResponse(
            id_evento_contacto=evento_contacto.id_evento_contacto,
            id_programacion_evento=evento_contacto.id_programacion_evento,
            id_contacto=evento_contacto.id_contacto,
            es_invitado=evento_contacto.id_contacto is None,
            nombre_completo=nombre_completo,
            numero_documento=numero_documento,
            correo=correo,
            celular=celular,
            id_empresa=detalle.empresa.id_empresa,
            nombre_empresa=detalle.empresa.nombre_empresa,
            estado=evento_contacto.estado,
            requiere_coordinacion=evento_contacto.requiere_coordinacion,
            asistencia_evento=evento_contacto.asistencia_evento,
            hora_ingreso=evento_contacto.hora_ingreso,
            credencial_impresa=evento_contacto.credencial_impresa,
            id_beneficio_asignado=detalle.id_beneficio_asignado,
            nombre_beneficio_asignado=detalle.nombre_beneficio_asignado,
            qr_enviado=detalle.qr_enviado,
        )

    @staticmethod
    def _evento_empresa_values(evento_empresa: EventoEmpresa) -> dict[str, Any]:
        return {
            "id_evento_empresa": evento_empresa.id_evento_empresa,
            "id_programacion_evento": evento_empresa.id_programacion_evento,
            "id_empresa": evento_empresa.id_empresa,
            "id_contacto_principal": evento_empresa.id_contacto_principal,
            "estado": evento_empresa.estado,
        }

    @staticmethod
    def _evento_contacto_values(evento_contacto: EventoContacto) -> dict[str, Any]:
        return {
            "id_evento_contacto": evento_contacto.id_evento_contacto,
            "id_programacion_evento": evento_contacto.id_programacion_evento,
            "id_contacto": evento_contacto.id_contacto,
            "id_empresa": evento_contacto.id_empresa,
            "estado": evento_contacto.estado,
            "requiere_coordinacion": evento_contacto.requiere_coordinacion,
            "asistencia_evento": evento_contacto.asistencia_evento,
            "hora_ingreso": (
                evento_contacto.hora_ingreso.isoformat()
                if evento_contacto.hora_ingreso
                else None
            ),
            "credencial_impresa": evento_contacto.credencial_impresa,
        }
