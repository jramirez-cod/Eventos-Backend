from datetime import UTC, date, datetime, time
from itertools import count

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auditoria.models import Auditoria
from app.modules.categorias.models import Categoria, DetalleCategoria
from app.modules.contactos.models import Contacto
from app.modules.empresas.models import Empresa, EmpresaHistorialClasificacion
from app.modules.eventos.models import (
    DetallePoliticaEvento,
    DetalleProgramacionEvento,
    Evento,
    EventoEstado,
    EventoModalidad,
    PoliticaEvento,
    ProgramacionEvento,
    ResponsableEvento,
)
from app.modules.grupos.models import Grupo
from app.modules.maestros.models import Area, Beneficio, Cargo, TipoCalculoBeneficio
from app.modules.participantes.models import (
    AsignacionBeneficio,
    EventoContacto,
    EventoEmpresa,
    ParticipanteQr,
)
from app.modules.usuarios.models import Usuario
from test.modules.usuarios.conftest import (  # noqa: F401
    auth_header,
    client,
    create_role,
    create_tipo_documento,
    create_user,
    grant_permission,
    session_factory,
)


REPORT_PERMISSIONS = (
    "CONSULTAR_REPORTE_EVENTO",
    "CONSULTAR_DATOS_PERSONALES_REPORTE",
    "EXPORTAR_REPORTE_EVENTO",
)
_sequence = count(1)


async def create_report_actor(
    session: AsyncSession,
    *,
    permissions: tuple[str, ...] = REPORT_PERMISSIONS,
    active: bool = True,
) -> tuple[Usuario, dict[str, str]]:
    seq = next(_sequence)
    role = await create_role(session, f"Rol reportes {seq}")
    for permission in permissions:
        await grant_permission(
            session,
            role,
            permiso_nombre=permission,
            modulo_nombre="REPORTES",
        )
    actor = await create_user(
        session,
        role,
        username=f"reporter.{seq}",
        estado=active,
    )
    await session.commit()
    return actor, auth_header(actor)


async def seed_report_context(session: AsyncSession) -> dict[str, object]:
    seq = next(_sequence)
    actor, headers = await create_report_actor(session)

    group_a = Grupo(id_grupo=10_000 + seq, nombre_grupo=f"Asociado {seq}", estado=True)
    group_b = Grupo(id_grupo=20_000 + seq, nombre_grupo=f"Expositor {seq}", estado=True)
    category_a = Categoria(nombre_categoria=f"Categoria A {seq}", estado=True)
    category_b = Categoria(nombre_categoria=f"Categoria B {seq}", estado=True)
    session.add_all([group_a, group_b, category_a, category_b])
    await session.flush()
    detail_a = DetalleCategoria(
        id_grupo=group_a.id_grupo, id_categoria=category_a.id_categoria, estado=True
    )
    detail_b = DetalleCategoria(
        id_grupo=group_b.id_grupo, id_categoria=category_b.id_categoria, estado=True
    )
    detail_shared = DetalleCategoria(
        id_grupo=group_b.id_grupo, id_categoria=category_a.id_categoria, estado=True
    )
    session.add_all([detail_a, detail_b, detail_shared])
    await session.flush()

    company = Empresa(
        id_detalle_categoria=detail_a.id_detalle_categoria,
        nombre_empresa=f"Empresa Principal {seq}",
        razon_social=f"Empresa Principal {seq} SAC",
        nombre_comercial=f"Principal {seq}",
        ruc=f"20{seq:09d}"[-11:],
        estado=True,
    )
    empty_company = Empresa(
        id_detalle_categoria=detail_shared.id_detalle_categoria,
        nombre_empresa=f"Empresa Sin Participantes {seq}",
        razon_social=f"Empresa Vacía {seq} SAC",
        nombre_comercial=None,
        ruc=f"21{seq:09d}"[-11:],
        estado=True,
    )
    session.add_all([company, empty_company])
    await session.flush()
    session.add_all(
        [
            EmpresaHistorialClasificacion(
                id_empresa=company.id_empresa,
                id_detalle_categoria=detail_b.id_detalle_categoria,
                fecha_inicio=datetime(2025, 1, 1, tzinfo=UTC),
                fecha_fin=datetime(2026, 2, 1, tzinfo=UTC),
            ),
            EmpresaHistorialClasificacion(
                id_empresa=company.id_empresa,
                id_detalle_categoria=detail_a.id_detalle_categoria,
                fecha_inicio=datetime(2026, 2, 1, tzinfo=UTC),
            ),
            EmpresaHistorialClasificacion(
                id_empresa=empty_company.id_empresa,
                id_detalle_categoria=detail_shared.id_detalle_categoria,
                fecha_inicio=datetime(2025, 1, 1, tzinfo=UTC),
            ),
        ]
    )

    area = Area(nombre_area=f"Área Reportes {seq}", descripcion="Reportes", estado=True)
    cargo = Cargo(nombre_cargo=f"Gerente Reportes {seq}", estado=True)
    per_event = Beneficio(
        nombre=f"Entrada Evento {seq}", tipo_calculo=TipoCalculoBeneficio.POR_EVENTO,
        personas_por_asignacion=1, estado=True,
    )
    annual = Beneficio(
        nombre=f"Entrada Anual {seq}", tipo_calculo=TipoCalculoBeneficio.POR_ANIO,
        personas_por_asignacion=1, estado=True,
    )
    no_benefit = Beneficio(
        nombre=f"Sin Beneficio Reporte {seq}", tipo_calculo=TipoCalculoBeneficio.SIN_BENEFICIO,
        personas_por_asignacion=1, estado=True,
    )
    session.add_all([area, cargo, per_event, annual, no_benefit])
    await session.flush()
    policy = PoliticaEvento(fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 12, 31))
    session.add(policy)
    await session.flush()
    session.add_all(
        [
            DetallePoliticaEvento(
                id_politica_evento=policy.id_politica_evento,
                id_beneficio=per_event.id_beneficio,
                id_categoria=category_a.id_categoria,
                entradas_gratuitas=2,
            ),
            DetallePoliticaEvento(
                id_politica_evento=policy.id_politica_evento,
                id_beneficio=annual.id_beneficio,
                id_categoria=category_a.id_categoria,
                entradas_gratuitas=1,
            ),
            DetallePoliticaEvento(
                id_politica_evento=policy.id_politica_evento,
                id_beneficio=no_benefit.id_beneficio,
                id_categoria=category_a.id_categoria,
                entradas_gratuitas=0,
            ),
        ]
    )
    event = Evento(
        id_politica_evento=policy.id_politica_evento,
        id_area=area.id_area,
        nombre_evento=f"Cumbre Reportes {seq}",
        descripcion="Evento integral para validar reportes",
        estado=EventoEstado.ABIERTO,
    )
    session.add(event)
    await session.flush()

    programs: list[ProgramacionEvento] = []
    for modality, event_date in (
        (EventoModalidad.HIBRIDO, date(2026, 1, 15)),
        (EventoModalidad.VIRTUAL, date(2026, 2, 15)),
        (EventoModalidad.PRESENCIAL, date(2026, 3, 15)),
    ):
        program = ProgramacionEvento(
            id_evento=event.id_evento,
            modalidad=modality,
            estado=EventoEstado.ABIERTO,
        )
        session.add(program)
        await session.flush()
        session.add(
            DetalleProgramacionEvento(
                id_programacion_evento=program.id_programacion_evento,
                fecha=event_date,
                hora_inicio=time(9),
                hora_fin=time(12),
                estado=True,
            )
        )
        programs.append(program)
    await session.flush()

    affiliations = [
        EventoEmpresa(
            id_evento=event.id_evento,
            id_empresa=company.id_empresa,
            estado=True,
            creado_por=actor.id_usuario,
        ),
        EventoEmpresa(
            id_evento=event.id_evento,
            id_empresa=empty_company.id_empresa,
            estado=True,
            creado_por=actor.id_usuario,
        ),
    ]
    session.add_all(affiliations)

    contact = Contacto(
        id_empresa=company.id_empresa,
        id_cargo=cargo.id_cargo,
        id_tipo_documento=actor.id_tipo_documento,
        numero_documento=f"7{seq:07d}"[-8:],
        nombres="Ana",
        apellidos="Zapata",
        genero="F",
        celular="987654321",
        correo=f"ana.{seq}@codip.pe",
        estado=True,
    )
    session.add(contact)
    await session.flush()
    master_participant = EventoContacto(
        id_programacion_evento=programs[0].id_programacion_evento,
        id_contacto=contact.id_contacto,
        id_empresa=company.id_empresa,
        estado=True,
        requiere_coordinacion=True,
        asistencia_evento=True,
        hora_ingreso=datetime(2026, 1, 15, 9, 10, tzinfo=UTC),
        credencial_impresa=True,
    )
    guest = EventoContacto(
        id_programacion_evento=programs[1].id_programacion_evento,
        id_empresa=company.id_empresa,
        invitado_nombres="Bruno",
        invitado_apellidos="Invitado",
        invitado_numero_documento="CE123456",
        invitado_correo=f"bruno.{seq}@example.com",
        invitado_celular="+51911111111",
        estado=True,
        asistencia_evento=False,
        credencial_impresa=False,
    )
    inactive_participant = EventoContacto(
        id_programacion_evento=programs[2].id_programacion_evento,
        id_contacto=contact.id_contacto,
        id_empresa=company.id_empresa,
        estado=False,
        asistencia_evento=True,
        credencial_impresa=False,
    )
    session.add_all([master_participant, guest, inactive_participant])
    await session.flush()
    session.add_all(
        [
            AsignacionBeneficio(
                id_evento_contacto=master_participant.id_evento_contacto,
                id_beneficio=annual.id_beneficio,
            ),
            AsignacionBeneficio(
                id_evento_contacto=guest.id_evento_contacto,
                id_beneficio=per_event.id_beneficio,
            ),
            ParticipanteQr(
                id_evento_contacto=master_participant.id_evento_contacto,
                codigo_seguro=f"qr-secret-sent-{seq}",
                fecha_generacion=datetime(2026, 1, 2, tzinfo=UTC),
                fecha_envio=datetime(2026, 1, 3, tzinfo=UTC),
                estado=True,
            ),
            ParticipanteQr(
                id_evento_contacto=guest.id_evento_contacto,
                codigo_seguro=f"qr-secret-pending-{seq}",
                fecha_generacion=datetime(2026, 2, 2, tzinfo=UTC),
                estado=True,
            ),
            ResponsableEvento(
                id_programacion_evento=programs[0].id_programacion_evento,
                id_usuario=actor.id_usuario,
                estado=True,
            ),
            Auditoria(
                id_usuario=actor.id_usuario,
                entidad="evento_contacto",
                id_entidad=str(master_participant.id_evento_contacto),
                accion="REIMPRESION_CREDENCIAL",
                valor_nuevo={"credencial_impresa": True},
            ),
        ]
    )
    await session.commit()
    return {
        "actor": actor,
        "headers": headers,
        "event": event,
        "programs": programs,
        "company": company,
        "empty_company": empty_company,
        "contact": contact,
        "cargo": cargo,
        "group_a": group_a,
        "group_b": group_b,
        "category_a": category_a,
        "category_b": category_b,
        "detail_a": detail_a,
        "detail_b": detail_b,
        "per_event": per_event,
        "annual": annual,
        "master_participant": master_participant,
        "guest": guest,
    }


__all__ = [
    "REPORT_PERMISSIONS",
    "create_report_actor",
    "seed_report_context",
]
