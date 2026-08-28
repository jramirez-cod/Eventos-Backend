from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.modules.eventos.models import EventoEstado, ProgramacionEvento
from app.modules.maestros.models import TipoCalculoBeneficio
from app.modules.participantes.models import EventoEmpresa, ParticipanteQr
from test.modules.contactos.conftest import create_contacto
from test.modules.participantes.conftest import (
    crear_contexto_beneficio,
    crear_programacion_con_dia,
    crear_responsable,
)
from test.modules.usuarios.conftest import create_role, create_user


pytestmark = pytest.mark.asyncio


async def test_programacion_finalizada_bloquea_todas_las_acciones(
    client, session_factory
) -> None:
    async with session_factory() as session:
        ctx = await crear_contexto_beneficio(
            session,
            tipo_calculo=TipoCalculoBeneficio.SIN_BENEFICIO,
        )
        prog = await crear_programacion_con_dia(
            session,
            evento=ctx["evento"],
            empresa=ctx["empresa"],
            fecha=date.today() + timedelta(days=5),
        )
        contacto = await create_contacto(
            session, empresa=ctx["empresa"], actor=ctx["actor"], sequence=40_301
        )
        role = await create_role(session, "Rol Responsable Bloqueo")
        usuario_responsable = await create_user(
            session, role, username="responsable.bloqueo"
        )
        await session.commit()

    headers = ctx["headers"]
    id_prog = prog.id_programacion_evento

    # Datos previos, todos creados mientras la programación aún está abierta.
    agregado = await client.post(
        f"/api/v1/participantes/programaciones/{id_prog}/evento-contactos",
        headers=headers,
        json={"ids_contacto": [contacto.id_contacto]},
    )
    assert agregado.status_code == 201, agregado.text
    id_ec = agregado.json()["evento_contactos"][0]["id_evento_contacto"]

    asignado = await client.post(
        "/api/v1/participantes/beneficios/asignar",
        headers=headers,
        json={"ids_evento_contacto": [id_ec], "id_beneficio": ctx["beneficio"].id_beneficio},
    )
    assert asignado.status_code == 201, asignado.text

    async with session_factory() as session:
        evento_empresa = await session.scalar(
            select(EventoEmpresa).where(
                EventoEmpresa.id_programacion_evento == id_prog,
                EventoEmpresa.id_empresa == ctx["empresa"].id_empresa,
            )
        )
        id_evento_empresa = evento_empresa.id_evento_empresa
        qr = await session.scalar(
            select(ParticipanteQr).where(
                ParticipanteQr.id_evento_contacto == id_ec
            )
        )
        codigo_seguro = qr.codigo_seguro
        await crear_responsable(session, programacion=prog, usuario=usuario_responsable)

    # Ahora finalizamos la programación directamente en BD (el actor de este
    # test solo tiene permisos de PARTICIPANTES, no de EVENTOS).
    async with session_factory() as session:
        prog_row = await session.get(ProgramacionEvento, id_prog)
        prog_row.estado = EventoEstado.FINALIZADO
        await session.commit()

    # A partir de aquí, absolutamente nada debe funcionar.
    checks: list[tuple[str, object]] = []

    checks.append(("contacto-principal", await client.patch(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/contacto-principal",
        headers=headers,
        json={"id_contacto": contacto.id_contacto},
    )))
    checks.append(("enviar-codigo-masivo", await client.post(
        f"/api/v1/participantes/programaciones/{id_prog}/empresas/enviar-codigo-masivo",
        headers=headers,
    )))
    checks.append(("reenviar-codigo", await client.post(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/reenviar-codigo",
        headers=headers,
        json={},
    )))
    checks.append(("desafiliar-empresa", await client.delete(
        f"/api/v1/participantes/empresas/{id_evento_empresa}",
        headers=headers,
    )))
    checks.append(("eliminar-invitado", await client.delete(
        f"/api/v1/participantes/evento-contactos/{id_ec}",
        headers=headers,
    )))
    checks.append(("asistencia", await client.patch(
        f"/api/v1/participantes/evento-contactos/{id_ec}/asistencia",
        headers=headers,
    )))
    checks.append(("estado-participante", await client.patch(
        f"/api/v1/participantes/evento-contactos/{id_ec}/estado",
        headers=headers,
        json={"estado": False},
    )))
    checks.append(("remover-beneficio", await client.delete(
        f"/api/v1/participantes/evento-contactos/{id_ec}/beneficio",
        headers=headers,
    )))
    checks.append(("enviar-qr", await client.post(
        f"/api/v1/participantes/evento-contactos/{id_ec}/qr/enviar",
        headers=headers,
    )))
    checks.append(("enviar-qr-masivo", await client.post(
        f"/api/v1/participantes/programaciones/{id_prog}/qr/enviar-masivo",
        headers=headers,
    )))
    checks.append(("imprimir-credencial", await client.post(
        f"/api/v1/participantes/qr/{codigo_seguro}/imprimir",
        headers=headers,
    )))
    checks.append(("reimprimir-credencial", await client.post(
        f"/api/v1/participantes/evento-contactos/{id_ec}/reimprimir",
        headers=headers,
        json={
            "id_responsable_evento": 1,
            "password": "no-importa",
        },
    )))

    for nombre, response in checks:
        assert response.status_code == 409, f"{nombre}: {response.text}"

    async with session_factory() as session:
        prog_final = await session.get(ProgramacionEvento, id_prog)
        assert prog_final.estado == EventoEstado.FINALIZADO
