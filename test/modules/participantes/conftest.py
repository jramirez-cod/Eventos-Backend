from datetime import date, timedelta
from itertools import count

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contactos.models import Contacto
from app.modules.empresas.models import Empresa
from app.modules.eventos.models import Evento, EventoEstado
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


async def create_evento(
    session: AsyncSession,
    *,
    actor: Usuario,
    sequence: int | None = None,
    estado: EventoEstado = EventoEstado.ABIERTO,
) -> Evento:
    sequence = sequence or next_sequence()
    evento = Evento(
        nombre_evento=f"Evento Participantes {sequence}",
        descripcion="Evento de prueba",
        fecha_inicio=date.today() + timedelta(days=10),
        fecha_fin=date.today() + timedelta(days=11),
        aforo=100,
        estado=estado,
        creado_por=actor.id_usuario,
    )
    session.add(evento)
    await session.flush()
    return evento


async def afiliar_empresa_http(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    evento: Evento,
    empresa: Empresa,
) -> dict[str, object]:
    response = await client.post(
        f"/api/v1/participantes/eventos/{evento.id_evento}/empresas",
        headers=headers,
        json={"id_empresa": empresa.id_empresa},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def participante_context(
    session: AsyncSession,
    client: AsyncClient,
    *,
    sequence: int | None = None,
    evento_estado: EventoEstado = EventoEstado.ABIERTO,
    empresa_estado: bool = True,
    contacto_estado: bool = True,
) -> tuple[Usuario, dict[str, str], Evento, Empresa, Contacto, dict[str, object]]:
    sequence = sequence or next_sequence()
    actor, headers = await seed_participante_actor(
        session,
        username=f"actor.participantes.{sequence}",
    )
    evento = await create_evento(
        session,
        actor=actor,
        sequence=sequence,
        estado=evento_estado,
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
        evento=evento,
        empresa=empresa,
    )
    return actor, headers, evento, empresa, contacto, afiliacion


def contacto_desde_evento_payload(
    *,
    actor: Usuario,
    empresa: Empresa,
    id_evento_empresa: int,
    sequence: int | None = None,
) -> dict[str, object]:
    sequence = sequence or next_sequence()
    return {
        "id_evento_empresa": id_evento_empresa,
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
    "create_evento",
    "next_sequence",
    "participante_context",
    "seed_participante_actor",
]
