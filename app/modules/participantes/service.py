import math
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auditoria.repository import AuditoriaRepository
from app.modules.contactos.service import ContactoService
from app.modules.empresas.models import Empresa
from app.modules.eventos.models import Evento
from app.modules.eventos.service import EventoNotEditableError, EventoService
from app.modules.participantes.dto import (
    ContactoDesdeEventoCreate,
    EventoEmpresaResponse,
    ParticipanteCreateMultiple,
    ParticipanteCreateResponse,
    ParticipanteListResponse,
    ParticipanteResponse,
)
from app.modules.participantes.models import (
    ConfirmacionParticipante,
    EventoEmpresa,
    Participante,
)
from app.modules.participantes.repository import (
    EventoEmpresaDetalle,
    ParticipanteDetalle,
    ParticipanteRepository,
)
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.repository import UsuarioRepository


MODULO_PARTICIPANTES = "PARTICIPANTES"


class ParticipanteServiceError(Exception):
    pass


class EventoNotFoundError(ParticipanteServiceError):
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


class ContactoEmpresaMismatchError(ParticipanteServiceError):
    pass


class DuplicateParticipanteError(ParticipanteServiceError):
    pass


class ParticipanteNotFoundError(ParticipanteServiceError):
    pass


class ParticipantePersistenceConflictError(ParticipanteServiceError):
    pass


class ParticipanteService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.participantes = ParticipanteRepository(db)
        self.contactos = ContactoService(db)
        self.usuarios = UsuarioRepository(db)
        self.auditoria = AuditoriaRepository(db)

    async def afiliar_empresa_evento(
        self, *, id_evento: int, id_empresa: int, actor: Usuario
    ) -> EventoEmpresaResponse:
        await self._get_open_event(id_evento)
        await self._get_active_company(id_empresa)
        if await self.participantes.get_evento_empresa(
            id_evento=id_evento, id_empresa=id_empresa
        ):
            raise DuplicateEventoEmpresaError(
                "La empresa ya está afiliada al evento."
            )

        try:
            evento_empresa = await self.participantes.create_evento_empresa(
                id_evento=id_evento,
                id_empresa=id_empresa,
                creado_por=actor.id_usuario,
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="evento_empresa",
                id_entidad=evento_empresa.id_evento_empresa,
                accion="AFILIAR_EMPRESA_EVENTO",
                valor_nuevo=self._evento_empresa_values(evento_empresa),
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise DuplicateEventoEmpresaError(
                "La empresa ya está afiliada al evento."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

        return await self._get_evento_empresa_response(
            evento_empresa.id_evento_empresa
        )

    async def listar_empresas_evento(
        self, id_evento: int
    ) -> list[EventoEmpresaResponse]:
        if await self.participantes.get_evento(id_evento) is None:
            raise EventoNotFoundError("Evento no encontrado.")
        rows = await self.participantes.list_empresas_evento(id_evento)
        return [self._evento_empresa_response(row) for row in rows]

    async def agregar_participantes(
        self,
        *,
        id_evento: int,
        data: ParticipanteCreateMultiple,
        actor: Usuario,
    ) -> ParticipanteCreateResponse:
        await self._get_open_event(id_evento)
        evento_empresa = await self._get_evento_empresa(
            id_evento=id_evento,
            id_evento_empresa=data.id_evento_empresa,
            for_update=True,
        )
        await self._get_active_company(evento_empresa.id_empresa)
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
            if contacto.id_empresa != evento_empresa.id_empresa:
                raise ContactoEmpresaMismatchError(
                    f"El contacto {contacto.id_contacto} no pertenece a la empresa afiliada."
                )

        await self.validar_participantes_no_duplicados(
            id_evento=id_evento,
            ids_contacto=data.ids_contacto,
        )

        created_ids: list[int] = []
        try:
            for id_contacto in data.ids_contacto:
                participante = await self.participantes.create_participante(
                    id_evento_empresa=evento_empresa.id_evento_empresa,
                    id_evento=id_evento,
                    id_contacto=id_contacto,
                    creado_por=actor.id_usuario,
                )
                created_ids.append(participante.id_participante)
                await self.auditoria.create(
                    id_usuario=actor.id_usuario,
                    id_modulo=await self._id_modulo(),
                    entidad="participante",
                    id_entidad=participante.id_participante,
                    accion="AGREGAR_PARTICIPANTE_EVENTO",
                    valor_nuevo=self._participante_values(participante),
                )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise DuplicateParticipanteError(
                "Uno de los contactos ya participa en el evento."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

        responses = [
            await self.obtener_participante(id_participante)
            for id_participante in created_ids
        ]
        return ParticipanteCreateResponse(
            created=len(responses), participantes=responses
        )

    async def crear_contacto_y_participante(
        self,
        *,
        id_evento: int,
        data: ContactoDesdeEventoCreate,
        actor: Usuario,
    ) -> ParticipanteResponse:
        await self._get_open_event(id_evento)
        evento_empresa = await self._get_evento_empresa(
            id_evento=id_evento,
            id_evento_empresa=data.id_evento_empresa,
            for_update=True,
        )
        await self._get_active_company(evento_empresa.id_empresa)
        if data.contacto.id_empresa != evento_empresa.id_empresa:
            raise ContactoEmpresaMismatchError(
                "La empresa del contacto no coincide con la empresa afiliada."
            )

        try:
            contacto = await self.contactos.crear_contacto(
                data=data.contacto,
                actor=actor,
                commit=False,
            )
            participante = await self.participantes.create_participante(
                id_evento_empresa=evento_empresa.id_evento_empresa,
                id_evento=id_evento,
                id_contacto=contacto.id_contacto,
                creado_por=actor.id_usuario,
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="participante",
                id_entidad=participante.id_participante,
                accion="CREAR_CONTACTO_DESDE_EVENTO",
                valor_nuevo={
                    **self._participante_values(participante),
                    "contacto_creado": contacto.id_contacto,
                },
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ParticipantePersistenceConflictError(
                "No se pudo crear el contacto y participante por un conflicto de datos."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

        return await self.obtener_participante(participante.id_participante)

    async def obtener_participante(
        self, id_participante: int
    ) -> ParticipanteResponse:
        detalle = await self.participantes.get_participante_detalle(id_participante)
        if detalle is None:
            raise ParticipanteNotFoundError("Participante no encontrado.")
        return self._participante_response(detalle)

    async def listar_participantes(
        self,
        *,
        id_evento: int | None,
        id_empresa: int | None,
        id_contacto: int | None,
        confirmacion: ConfirmacionParticipante | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> ParticipanteListResponse:
        rows, total = await self.participantes.list_participantes(
            id_evento=id_evento,
            id_empresa=id_empresa,
            id_contacto=id_contacto,
            confirmacion=confirmacion,
            search=search,
            page=page,
            page_size=page_size,
        )
        return ParticipanteListResponse(
            items=[self._participante_response(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def validar_participantes_no_duplicados(
        self, *, id_evento: int, ids_contacto: list[int]
    ) -> None:
        existing = await self.participantes.get_existing_contact_ids(
            id_evento=id_evento,
            ids_contacto=ids_contacto,
        )
        if existing:
            raise DuplicateParticipanteError(
                "Los siguientes contactos ya participan en el evento: "
                f"{', '.join(map(str, sorted(existing)))}."
            )

    async def _get_open_event(self, id_evento: int) -> Evento:
        evento = await self.participantes.get_evento_for_update(id_evento)
        if evento is None:
            raise EventoNotFoundError("Evento no encontrado.")
        try:
            EventoService.validar_evento_abierto(evento)
        except EventoNotEditableError as exc:
            raise EventoNotOpenError(
                "El evento debe estar ABIERTO para ejecutar esta operación."
            ) from exc
        return evento

    async def _get_active_company(self, id_empresa: int) -> Empresa:
        empresa = await self.participantes.get_empresa(id_empresa)
        if empresa is None:
            raise EmpresaNotFoundError("Empresa no encontrada.")
        if not empresa.estado:
            raise EmpresaInactiveError("La empresa se encuentra inactiva.")
        return empresa

    async def _get_evento_empresa(
        self,
        *,
        id_evento: int,
        id_evento_empresa: int,
        for_update: bool,
    ) -> EventoEmpresa:
        evento_empresa = await self.participantes.get_evento_empresa_by_id(
            id_evento_empresa,
            id_evento=id_evento,
            for_update=for_update,
        )
        if evento_empresa is None or not evento_empresa.estado:
            raise EventoEmpresaNotFoundError(
                "La empresa no está afiliada activamente al evento."
            )
        return evento_empresa

    async def _get_evento_empresa_response(
        self, id_evento_empresa: int
    ) -> EventoEmpresaResponse:
        detalle = await self.participantes.get_evento_empresa_detalle(
            id_evento_empresa
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
            id_evento=relation.id_evento,
            id_empresa=relation.id_empresa,
            nombre_empresa=detalle.empresa.nombre_empresa,
            ruc=detalle.empresa.ruc,
            id_grupo=detalle.grupo.id_grupo,
            nombre_grupo=detalle.grupo.nombre_grupo,
            id_categoria=detalle.categoria.id_categoria,
            nombre_categoria=detalle.categoria.nombre_categoria,
            estado=relation.estado,
            creado_en=relation.creado_en,
            creado_por=relation.creado_por,
        )

    @staticmethod
    def _participante_response(
        detalle: ParticipanteDetalle,
    ) -> ParticipanteResponse:
        participante = detalle.participante
        contacto = detalle.contacto
        return ParticipanteResponse(
            id_participante=participante.id_participante,
            id_evento_empresa=participante.id_evento_empresa,
            id_evento=participante.id_evento,
            nombre_evento=detalle.evento.nombre_evento,
            id_empresa=detalle.empresa.id_empresa,
            nombre_empresa=detalle.empresa.nombre_empresa,
            id_contacto=contacto.id_contacto,
            nombre_completo=contacto.nombre_completo,
            numero_documento=contacto.numero_documento,
            correo=contacto.correo,
            celular=contacto.celular,
            confirmacion=participante.confirmacion,
            estado=participante.estado,
            creado_en=participante.creado_en,
            creado_por=participante.creado_por,
        )

    @staticmethod
    def _evento_empresa_values(
        evento_empresa: EventoEmpresa,
    ) -> dict[str, Any]:
        return {
            "id_evento_empresa": evento_empresa.id_evento_empresa,
            "id_evento": evento_empresa.id_evento,
            "id_empresa": evento_empresa.id_empresa,
            "estado": evento_empresa.estado,
        }

    @staticmethod
    def _participante_values(participante: Participante) -> dict[str, Any]:
        return {
            "id_participante": participante.id_participante,
            "id_evento_empresa": participante.id_evento_empresa,
            "id_evento": participante.id_evento,
            "id_contacto": participante.id_contacto,
            "confirmacion": participante.confirmacion.value,
            "estado": participante.estado,
        }
