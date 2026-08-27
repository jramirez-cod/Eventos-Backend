from datetime import UTC, date, datetime, time, timedelta
from itertools import count

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.modules.categorias.models import Categoria, DetalleCategoria
from app.modules.contactos.models import Contacto
from app.modules.empresas.models import Empresa
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
from app.modules.maestros.models import Area, Beneficio, TipoCalculoBeneficio
from app.modules.participantes.models import CodigoAccesoPrincipal, EventoEmpresa
from app.modules.usuarios.models import Usuario
from test.modules.contactos.conftest import create_contacto, create_empresa
from test.modules.usuarios.conftest import (
    auth_header,
    create_role,
    create_user,
    grant_permission,
)


PARTICIPANTE_PERMISSIONS = (
    "CONSULTAR_PARTICIPANTE",
    "CREAR_PARTICIPANTE",
    "AFILIAR_EMPRESA_EVENTO",
)

_sequence = count(1)


def next_sequence() -> int:
    return next(_sequence)


async def seed_participante_actor(
    session: AsyncSession,
    *,
    username: str = "actor.participantes",
    permissions: tuple[str, ...] = PARTICIPANTE_PERMISSIONS,
) -> tuple[Usuario, dict[str, str]]:
    role = await create_role(session, f"Rol {username}")
    for permission in permissions:
        await grant_permission(
            session,
            role,
            permiso_nombre=permission,
            modulo_nombre="PARTICIPANTES",
        )
    actor = await create_user(session, role, username=username)
    await session.commit()
    return actor, auth_header(actor)


async def create_programacion(
    session: AsyncSession,
    *,
    sequence: int | None = None,
    evento_estado: EventoEstado = EventoEstado.ABIERTO,
) -> ProgramacionEvento:
    sequence = sequence or next_sequence()
    area = Area(nombre_area=f"Area Participantes {sequence}", estado=True)
    beneficio = Beneficio(nombre=f"Beneficio Participantes {sequence}", estado=True)
    categoria = Categoria(
        nombre_categoria=f"Categoria Participantes {sequence}", estado=True
    )
    session.add_all([area, beneficio, categoria])
    await session.flush()

    politica = PoliticaEvento(
        fecha_inicio=date.today() + timedelta(days=10),
        fecha_fin=date.today() + timedelta(days=11),
    )
    session.add(politica)
    await session.flush()

    evento = Evento(
        nombre_evento=f"Evento Participantes {sequence}",
        descripcion="Evento de prueba",
        id_politica_evento=politica.id_politica_evento,
        id_area=area.id_area,
        estado=evento_estado,
    )
    session.add(evento)
    await session.flush()

    programacion = ProgramacionEvento(
        id_evento=evento.id_evento,
        id_lugar=None,
        modalidad=EventoModalidad.VIRTUAL,
        enlace_general=None,
        estado=EventoEstado.ABIERTO,
    )
    session.add(programacion)
    await session.flush()

    session.add(
        DetalleProgramacionEvento(
            id_programacion_evento=programacion.id_programacion_evento,
            fecha=date.today() + timedelta(days=10),
            hora_inicio=time(9, 0),
            hora_fin=time(18, 0),
            enlace=None,
            estado=True,
        )
    )
    await session.flush()
    return programacion


async def afiliar_empresa_http(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    programacion: ProgramacionEvento,
    empresa: Empresa,
) -> dict[str, object]:
    response = await client.post(
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/empresas",
        headers=headers,
        json={"id_empresa": empresa.id_empresa},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def evento_contacto_context(
    session: AsyncSession,
    client: AsyncClient,
    *,
    sequence: int | None = None,
    evento_estado: EventoEstado = EventoEstado.ABIERTO,
    empresa_estado: bool = True,
    contacto_estado: bool = True,
) -> tuple[
    Usuario,
    dict[str, str],
    ProgramacionEvento,
    Empresa,
    Contacto,
    dict[str, object],
]:
    sequence = sequence or next_sequence()
    actor, headers = await seed_participante_actor(
        session,
        username=f"actor.participantes.{sequence}",
    )
    programacion = await create_programacion(
        session,
        sequence=sequence,
        evento_estado=evento_estado,
    )
    empresa = await create_empresa(
        session,
        sequence=20_000 + sequence,
        estado=empresa_estado,
    )
    contacto = await create_contacto(
        session,
        empresa=empresa,
        actor=actor,
        sequence=20_000 + sequence,
        estado=contacto_estado,
    )
    await session.commit()
    afiliacion = await afiliar_empresa_http(
        client,
        headers,
        programacion=programacion,
        empresa=empresa,
    )
    return actor, headers, programacion, empresa, contacto, afiliacion


async def crear_contexto_beneficio(
    session: AsyncSession,
    *,
    tipo_calculo: TipoCalculoBeneficio,
    personas_por_asignacion: int = 1,
    entradas_gratuitas: int = 1,
    politica_fecha_inicio: date | None = None,
    politica_fecha_fin: date | None = None,
    sequence: int | None = None,
) -> dict[str, object]:
    sequence = sequence or next_sequence()
    actor, headers = await seed_participante_actor(
        session, username=f"actor.beneficio.{sequence}"
    )
    empresa = await create_empresa(session, sequence=30_000 + sequence)
    detalle_categoria = await session.get(
        DetalleCategoria, empresa.id_detalle_categoria
    )
    categoria = await session.get(Categoria, detalle_categoria.id_categoria)

    area = Area(nombre_area=f"Area Beneficio {sequence}", estado=True)
    beneficio = Beneficio(
        nombre=f"Beneficio {sequence}",
        tipo_calculo=tipo_calculo,
        personas_por_asignacion=personas_por_asignacion,
        estado=True,
    )
    session.add_all([area, beneficio])
    await session.flush()

    fecha_inicio = politica_fecha_inicio or (date.today() + timedelta(days=1))
    fecha_fin = politica_fecha_fin or (date.today() + timedelta(days=90))
    politica = PoliticaEvento(fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
    session.add(politica)
    await session.flush()
    session.add(
        DetallePoliticaEvento(
            id_politica_evento=politica.id_politica_evento,
            id_beneficio=beneficio.id_beneficio,
            id_categoria=categoria.id_categoria,
            entradas_gratuitas=entradas_gratuitas,
        )
    )
    evento = Evento(
        nombre_evento=f"Evento Beneficio {sequence}",
        descripcion="Evento de prueba de beneficios",
        id_politica_evento=politica.id_politica_evento,
        id_area=area.id_area,
        estado=EventoEstado.ABIERTO,
    )
    session.add(evento)
    await session.flush()
    await session.commit()

    return {
        "actor": actor,
        "headers": headers,
        "empresa": empresa,
        "categoria": categoria,
        "beneficio": beneficio,
        "evento": evento,
        "politica": politica,
    }


async def crear_programacion_con_dia(
    session: AsyncSession,
    *,
    evento: Evento,
    empresa: Empresa,
    fecha: date,
) -> ProgramacionEvento:
    programacion = ProgramacionEvento(
        id_evento=evento.id_evento,
        id_lugar=None,
        modalidad=EventoModalidad.VIRTUAL,
        enlace_general=None,
        estado=EventoEstado.ABIERTO,
    )
    session.add(programacion)
    await session.flush()
    session.add(
        DetalleProgramacionEvento(
            id_programacion_evento=programacion.id_programacion_evento,
            fecha=fecha,
            hora_inicio=time(9, 0),
            hora_fin=time(18, 0),
            enlace=None,
            estado=True,
        )
    )
    session.add(
        EventoEmpresa(
            id_programacion_evento=programacion.id_programacion_evento,
            id_empresa=empresa.id_empresa,
            estado=True,
        )
    )
    await session.commit()
    return programacion


async def crear_responsable(
    session: AsyncSession,
    *,
    programacion: ProgramacionEvento,
    usuario: Usuario,
) -> ResponsableEvento:
    responsable = ResponsableEvento(
        id_programacion_evento=programacion.id_programacion_evento,
        id_usuario=usuario.id_usuario,
        estado=True,
    )
    session.add(responsable)
    await session.commit()
    await session.refresh(responsable)
    return responsable


async def create_codigo_acceso(
    session: AsyncSession,
    *,
    id_evento_empresa: int,
    codigo: str = "ABCD1234",
    expira_en: datetime | None = None,
    fecha_envio: datetime | None = None,
    estado: bool = True,
) -> str:
    registro = CodigoAccesoPrincipal(
        id_evento_empresa=id_evento_empresa,
        codigo_hash=security.hash_portal_code(codigo),
        expira_en=expira_en or datetime.now(UTC) + timedelta(days=5),
        fecha_envio=fecha_envio,
        estado=estado,
    )
    session.add(registro)
    await session.commit()
    return codigo


def contacto_desde_evento_payload(
    *,
    actor: Usuario,
    empresa: Empresa,
    sequence: int | None = None,
) -> dict[str, object]:
    sequence = sequence or next_sequence()
    return {
        "contacto": {
            "id_empresa": empresa.id_empresa,
            "id_cargo": None,
            "id_tipo_documento": actor.id_tipo_documento,
            "numero_documento": f"8{sequence:07d}",
            "nombres": f"Nuevo {sequence}",
            "apellidos": f"Participante {sequence}",
            "genero": "M",
            "celular": "987 654 321",
            "correo": f"nuevo.participante.{sequence}@example.com",
            "es_contacto_principal": False,
        },
    }


__all__ = [
    "PARTICIPANTE_PERMISSIONS",
    "afiliar_empresa_http",
    "contacto_desde_evento_payload",
    "create_codigo_acceso",
    "crear_contexto_beneficio",
    "crear_programacion_con_dia",
    "crear_responsable",
    "create_programacion",
    "evento_contacto_context",
    "next_sequence",
    "seed_participante_actor",
]
