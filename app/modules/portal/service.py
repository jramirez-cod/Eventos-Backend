from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.modules.contactos.service import ContactoService
from app.modules.eventos.models import EventoEstado
from app.modules.eventos.repository import EventoRepository
from app.modules.participantes.dto import (
    AsignarBeneficioRequest,
    EventoContactoCreateMultiple,
    EventoContactoResponse,
    InvitadoCreate,
)
from app.modules.participantes.repository import ParticipanteRepository
from app.modules.participantes.service import ParticipanteService
from app.modules.portal.dto import (
    AgregarParticipantesPortalRequest,
    PortalContactoDisponible,
    ValidarCodigoResponse,
)


class PortalServiceError(Exception):
    pass


class CodigoInvalidoError(PortalServiceError):
    pass


class PortalTokenInvalidoError(PortalServiceError):
    pass


class ContactoNoPerteneceEmpresaError(PortalServiceError):
    pass


@dataclass(frozen=True, slots=True)
class PortalContext:
    id_evento_empresa: int
    id_programacion_evento: int
    id_evento: int
    id_empresa: int
    id_categoria: int


class PortalService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.participantes = ParticipanteRepository(db)
        self.participante_service = ParticipanteService(db)
        self.contactos = ContactoService(db)
        self.eventos = EventoRepository(db)

    async def validar_codigo(self, codigo: str) -> ValidarCodigoResponse:
        codigo_hash = security.hash_portal_code(codigo)
        registro = await self.participantes.get_codigo_by_hash(codigo_hash)
        if registro is None:
            raise CodigoInvalidoError("Código inválido.")

        expira_en = registro.expira_en
        if expira_en.tzinfo is None:
            expira_en = expira_en.replace(tzinfo=timezone.utc)
        if expira_en <= datetime.now(timezone.utc):
            raise CodigoInvalidoError("El código expiró.")

        detalle = await self.participantes.get_evento_empresa_detalle(
            registro.id_evento_empresa
        )
        if detalle is None or detalle.contacto_principal is None:
            raise CodigoInvalidoError("Código inválido.")
        programacion = await self.participantes.get_programacion(
            detalle.evento_empresa.id_programacion_evento
        )
        assert programacion is not None
        evento = await self.eventos.get_by_id(programacion.id_evento)
        assert evento is not None
        if evento.estado != EventoEstado.ABIERTO:
            raise CodigoInvalidoError(
                "El código ya no es válido porque el evento no está abierto."
            )
        if programacion.estado != EventoEstado.ABIERTO:
            raise CodigoInvalidoError(
                "El código ya no es válido porque la programación no está abierta."
            )

        token = security.create_portal_access_token(
            detalle.evento_empresa.id_evento_empresa
        )
        return ValidarCodigoResponse(
            portal_token=token,
            nombre_empresa=detalle.empresa.nombre_empresa,
            nombre_evento=evento.nombre_evento,
            nombre_contacto_principal=detalle.contacto_principal.nombre_completo,
            nombre_categoria=detalle.categoria.nombre_categoria,
        )

    async def get_context(self, portal_token: str) -> PortalContext:
        try:
            payload = security.decode_portal_access_token(portal_token)
            id_evento_empresa = int(payload["sub"])
        except (ValueError, security.InvalidTokenError) as exc:
            raise PortalTokenInvalidoError("Sesión inválida o expirada.") from exc

        detalle = await self.participantes.get_evento_empresa_detalle(
            id_evento_empresa
        )
        if detalle is None:
            raise PortalTokenInvalidoError("Sesión inválida o expirada.")
        programacion = await self.participantes.get_programacion(
            detalle.evento_empresa.id_programacion_evento
        )
        assert programacion is not None
        evento = await self.eventos.get_by_id(programacion.id_evento)
        assert evento is not None
        if evento.estado != EventoEstado.ABIERTO or programacion.estado != EventoEstado.ABIERTO:
            raise PortalTokenInvalidoError(
                "El evento o la programación ya no está abierta."
            )
        return PortalContext(
            id_evento_empresa=id_evento_empresa,
            id_programacion_evento=detalle.evento_empresa.id_programacion_evento,
            id_evento=programacion.id_evento,
            id_empresa=detalle.empresa.id_empresa,
            id_categoria=detalle.categoria.id_categoria,
        )

    async def listar_contactos(
        self, context: PortalContext
    ) -> list[PortalContactoDisponible]:
        pagina = await self.contactos.listar_contactos(
            search=None,
            id_empresa=context.id_empresa,
            id_cargo=None,
            numero_documento=None,
            estado=True,
            page=1,
            page_size=200,
        )
        beneficios = await self.participante_service.beneficios_disponibles_para(
            id_programacion_evento=context.id_programacion_evento,
            id_evento=context.id_evento,
            id_empresa=context.id_empresa,
            id_categoria=context.id_categoria,
        )

        resultados: list[PortalContactoDisponible] = []
        for contacto in pagina.items:
            existente = (
                await self.participantes.get_evento_contacto_by_programacion_contacto(
                    id_programacion_evento=context.id_programacion_evento,
                    id_contacto=contacto.id_contacto,
                )
            )
            resultados.append(
                PortalContactoDisponible(
                    id_contacto=contacto.id_contacto,
                    nombre_completo=f"{contacto.nombres} {contacto.apellidos}",
                    numero_documento=contacto.numero_documento,
                    ya_agregado=existente is not None,
                    beneficios_disponibles=beneficios,
                )
            )
        return resultados

    async def agregar_participantes(
        self, context: PortalContext, data: AgregarParticipantesPortalRequest
    ) -> list[EventoContactoResponse]:
        for seleccion in data.selecciones:
            contacto = await self.participantes.get_contacto(seleccion.id_contacto)
            if contacto is None or contacto.id_empresa != context.id_empresa:
                raise ContactoNoPerteneceEmpresaError(
                    f"El contacto {seleccion.id_contacto} no pertenece a esta empresa."
                )

        creados = await self.participante_service.agregar_evento_contactos(
            id_programacion_evento=context.id_programacion_evento,
            data=EventoContactoCreateMultiple(
                ids_contacto=[s.id_contacto for s in data.selecciones]
            ),
            actor=None,
        )
        por_contacto = {
            evento_contacto.id_contacto: evento_contacto
            for evento_contacto in creados.evento_contactos
        }

        grupos_por_beneficio: dict[int, list[int]] = {}
        for seleccion in data.selecciones:
            if seleccion.id_beneficio is None:
                continue
            id_evento_contacto = por_contacto[seleccion.id_contacto].id_evento_contacto
            grupos_por_beneficio.setdefault(seleccion.id_beneficio, []).append(
                id_evento_contacto
            )

        actualizados_por_id: dict[int, EventoContactoResponse] = {}
        for id_beneficio, ids_evento_contacto in grupos_por_beneficio.items():
            actualizados = await self.participante_service.asignar_beneficio(
                data=AsignarBeneficioRequest(
                    ids_evento_contacto=ids_evento_contacto,
                    id_beneficio=id_beneficio,
                ),
                actor=None,
            )
            for actualizado in actualizados:
                actualizados_por_id[actualizado.id_evento_contacto] = actualizado

        return [
            actualizados_por_id.get(evento_contacto.id_evento_contacto, evento_contacto)
            for evento_contacto in por_contacto.values()
        ]

    async def agregar_invitado(
        self, context: PortalContext, data: InvitadoCreate
    ) -> EventoContactoResponse:
        return await self.participante_service.agregar_invitado_sin_registrar(
            id_programacion_evento=context.id_programacion_evento,
            id_empresa=context.id_empresa,
            data=data,
            actor=None,
        )
