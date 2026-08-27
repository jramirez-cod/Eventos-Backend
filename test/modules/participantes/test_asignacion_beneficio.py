from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.modules.auditoria.models import Auditoria
from app.modules.eventos.models import (
    DetallePoliticaEvento,
    EventoEstado,
    ProgramacionEvento,
)
from app.modules.maestros.models import Beneficio, TipoCalculoBeneficio
from app.modules.participantes.models import ParticipanteQr
from test.modules.contactos.conftest import create_contacto
from test.modules.usuarios.conftest import VALID_PASSWORD
from test.modules.participantes.conftest import (
    crear_contexto_beneficio,
    crear_programacion_con_dia,
    crear_responsable,
)


pytestmark = pytest.mark.asyncio


async def _agregar_contacto(
    client, headers, *, id_programacion_evento: int, id_contacto: int
) -> int:
    response = await client.post(
        f"/api/v1/participantes/programaciones/{id_programacion_evento}/evento-contactos",
        headers=headers,
        json={"ids_contacto": [id_contacto]},
    )
    assert response.status_code == 201, response.text
    return response.json()["evento_contactos"][0]["id_evento_contacto"]


async def test_por_evento_consume_cupo_de_la_ocurrencia_sin_importar_asistencia(
    client, session_factory
) -> None:
    async with session_factory() as session:
        ctx = await crear_contexto_beneficio(
            session,
            tipo_calculo=TipoCalculoBeneficio.POR_EVENTO,
            entradas_gratuitas=1,
        )
        prog_a = await crear_programacion_con_dia(
            session,
            evento=ctx["evento"],
            empresa=ctx["empresa"],
            fecha=date.today() + timedelta(days=5),
        )
        prog_b = await crear_programacion_con_dia(
            session,
            evento=ctx["evento"],
            empresa=ctx["empresa"],
            fecha=date.today() + timedelta(days=15),
        )
        contacto1 = await create_contacto(
            session, empresa=ctx["empresa"], actor=ctx["actor"], sequence=31_001
        )
        contacto2 = await create_contacto(
            session, empresa=ctx["empresa"], actor=ctx["actor"], sequence=31_002
        )
        await session.commit()

    headers = ctx["headers"]
    id_ec1 = await _agregar_contacto(
        client,
        headers,
        id_programacion_evento=prog_a.id_programacion_evento,
        id_contacto=contacto1.id_contacto,
    )
    id_ec2 = await _agregar_contacto(
        client,
        headers,
        id_programacion_evento=prog_a.id_programacion_evento,
        id_contacto=contacto2.id_contacto,
    )

    ok = await client.post(
        "/api/v1/participantes/beneficios/asignar",
        headers=headers,
        json={
            "ids_evento_contacto": [id_ec1],
            "id_beneficio": ctx["beneficio"].id_beneficio,
        },
    )
    assert ok.status_code == 201, ok.text

    agotado = await client.post(
        "/api/v1/participantes/beneficios/asignar",
        headers=headers,
        json={
            "ids_evento_contacto": [id_ec2],
            "id_beneficio": ctx["beneficio"].id_beneficio,
        },
    )
    assert agotado.status_code == 409, agotado.text

    id_ec3 = await _agregar_contacto(
        client,
        headers,
        id_programacion_evento=prog_b.id_programacion_evento,
        id_contacto=contacto2.id_contacto,
    )
    otra_ocurrencia = await client.post(
        "/api/v1/participantes/beneficios/asignar",
        headers=headers,
        json={
            "ids_evento_contacto": [id_ec3],
            "id_beneficio": ctx["beneficio"].id_beneficio,
        },
    )
    assert otra_ocurrencia.status_code == 201, otra_ocurrencia.text


async def test_por_anio_solo_cuenta_si_asistio(client, session_factory) -> None:
    async with session_factory() as session:
        ctx = await crear_contexto_beneficio(
            session,
            tipo_calculo=TipoCalculoBeneficio.POR_ANIO,
            entradas_gratuitas=1,
        )
        prog_a = await crear_programacion_con_dia(
            session,
            evento=ctx["evento"],
            empresa=ctx["empresa"],
            fecha=date.today() + timedelta(days=5),
        )
        prog_b = await crear_programacion_con_dia(
            session,
            evento=ctx["evento"],
            empresa=ctx["empresa"],
            fecha=date.today() + timedelta(days=15),
        )
        prog_c = await crear_programacion_con_dia(
            session,
            evento=ctx["evento"],
            empresa=ctx["empresa"],
            fecha=date.today() + timedelta(days=25),
        )
        contacto1 = await create_contacto(
            session, empresa=ctx["empresa"], actor=ctx["actor"], sequence=32_001
        )
        contacto2 = await create_contacto(
            session, empresa=ctx["empresa"], actor=ctx["actor"], sequence=32_002
        )
        contacto3 = await create_contacto(
            session, empresa=ctx["empresa"], actor=ctx["actor"], sequence=32_003
        )
        await session.commit()

    headers = ctx["headers"]
    id_beneficio = ctx["beneficio"].id_beneficio

    id_ec1 = await _agregar_contacto(
        client,
        headers,
        id_programacion_evento=prog_a.id_programacion_evento,
        id_contacto=contacto1.id_contacto,
    )
    primero = await client.post(
        "/api/v1/participantes/beneficios/asignar",
        headers=headers,
        json={"ids_evento_contacto": [id_ec1], "id_beneficio": id_beneficio},
    )
    assert primero.status_code == 201, primero.text
    # contacto1 nunca asiste: no debe consumir el cupo.

    id_ec2 = await _agregar_contacto(
        client,
        headers,
        id_programacion_evento=prog_b.id_programacion_evento,
        id_contacto=contacto2.id_contacto,
    )
    segundo = await client.post(
        "/api/v1/participantes/beneficios/asignar",
        headers=headers,
        json={"ids_evento_contacto": [id_ec2], "id_beneficio": id_beneficio},
    )
    assert segundo.status_code == 201, segundo.text

    asistencia = await client.patch(
        f"/api/v1/participantes/evento-contactos/{id_ec2}/asistencia",
        headers=headers,
    )
    assert asistencia.status_code == 200, asistencia.text

    id_ec3 = await _agregar_contacto(
        client,
        headers,
        id_programacion_evento=prog_c.id_programacion_evento,
        id_contacto=contacto3.id_contacto,
    )
    tercero = await client.post(
        "/api/v1/participantes/beneficios/asignar",
        headers=headers,
        json={"ids_evento_contacto": [id_ec3], "id_beneficio": id_beneficio},
    )
    assert tercero.status_code == 409, tercero.text


async def test_sin_beneficio_siempre_disponible(client, session_factory) -> None:
    async with session_factory() as session:
        ctx = await crear_contexto_beneficio(
            session,
            tipo_calculo=TipoCalculoBeneficio.SIN_BENEFICIO,
            entradas_gratuitas=0,
        )
        prog = await crear_programacion_con_dia(
            session,
            evento=ctx["evento"],
            empresa=ctx["empresa"],
            fecha=date.today() + timedelta(days=5),
        )
        contacto1 = await create_contacto(
            session, empresa=ctx["empresa"], actor=ctx["actor"], sequence=33_001
        )
        contacto2 = await create_contacto(
            session, empresa=ctx["empresa"], actor=ctx["actor"], sequence=33_002
        )
        await session.commit()

    headers = ctx["headers"]
    for contacto in (contacto1, contacto2):
        id_ec = await _agregar_contacto(
            client,
            headers,
            id_programacion_evento=prog.id_programacion_evento,
            id_contacto=contacto.id_contacto,
        )
        response = await client.post(
            "/api/v1/participantes/beneficios/asignar",
            headers=headers,
            json={
                "ids_evento_contacto": [id_ec],
                "id_beneficio": ctx["beneficio"].id_beneficio,
            },
        )
        assert response.status_code == 201, response.text


async def test_grupo_todo_o_nada_en_beneficio_por_anio(
    client, session_factory
) -> None:
    async with session_factory() as session:
        ctx = await crear_contexto_beneficio(
            session,
            tipo_calculo=TipoCalculoBeneficio.POR_ANIO,
            personas_por_asignacion=2,
            entradas_gratuitas=1,  # 1 cupo = 1 pareja = 2 entradas individuales
        )
        prog_a = await crear_programacion_con_dia(
            session,
            evento=ctx["evento"],
            empresa=ctx["empresa"],
            fecha=date.today() + timedelta(days=5),
        )
        prog_b = await crear_programacion_con_dia(
            session,
            evento=ctx["evento"],
            empresa=ctx["empresa"],
            fecha=date.today() + timedelta(days=15),
        )
        contactos = [
            await create_contacto(
                session,
                empresa=ctx["empresa"],
                actor=ctx["actor"],
                sequence=34_000 + i,
            )
            for i in range(6)
        ]
        await session.commit()

    headers = ctx["headers"]
    id_beneficio = ctx["beneficio"].id_beneficio

    id_ec1 = await _agregar_contacto(
        client,
        headers,
        id_programacion_evento=prog_a.id_programacion_evento,
        id_contacto=contactos[0].id_contacto,
    )
    id_ec2 = await _agregar_contacto(
        client,
        headers,
        id_programacion_evento=prog_a.id_programacion_evento,
        id_contacto=contactos[1].id_contacto,
    )
    pareja1 = await client.post(
        "/api/v1/participantes/beneficios/asignar",
        headers=headers,
        json={"ids_evento_contacto": [id_ec1, id_ec2], "id_beneficio": id_beneficio},
    )
    assert pareja1.status_code == 201, pareja1.text

    # Solo asiste uno de los dos: el grupo no debe consumir el cupo todavía.
    await client.patch(
        f"/api/v1/participantes/evento-contactos/{id_ec1}/asistencia",
        headers=headers,
    )

    id_ec3 = await _agregar_contacto(
        client,
        headers,
        id_programacion_evento=prog_b.id_programacion_evento,
        id_contacto=contactos[2].id_contacto,
    )
    id_ec4 = await _agregar_contacto(
        client,
        headers,
        id_programacion_evento=prog_b.id_programacion_evento,
        id_contacto=contactos[3].id_contacto,
    )
    pareja2 = await client.post(
        "/api/v1/participantes/beneficios/asignar",
        headers=headers,
        json={"ids_evento_contacto": [id_ec3, id_ec4], "id_beneficio": id_beneficio},
    )
    assert pareja2.status_code == 201, pareja2.text

    # Ahora completamos la asistencia de la primera pareja: recién ahí consume
    # las 2 entradas individuales del único cupo configurado (entradas_gratuitas=1).
    completar = await client.patch(
        f"/api/v1/participantes/evento-contactos/{id_ec2}/asistencia",
        headers=headers,
    )
    assert completar.status_code == 200, completar.text

    id_ec5 = await _agregar_contacto(
        client,
        headers,
        id_programacion_evento=prog_a.id_programacion_evento,
        id_contacto=contactos[4].id_contacto,
    )
    id_ec6 = await _agregar_contacto(
        client,
        headers,
        id_programacion_evento=prog_a.id_programacion_evento,
        id_contacto=contactos[5].id_contacto,
    )
    pareja3 = await client.post(
        "/api/v1/participantes/beneficios/asignar",
        headers=headers,
        json={"ids_evento_contacto": [id_ec5, id_ec6], "id_beneficio": id_beneficio},
    )
    assert pareja3.status_code == 409, pareja3.text


async def test_impresion_credencial_solo_una_vez(client, session_factory) -> None:
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
            session, empresa=ctx["empresa"], actor=ctx["actor"], sequence=35_001
        )
        await session.commit()

    headers = ctx["headers"]
    id_ec = await _agregar_contacto(
        client,
        headers,
        id_programacion_evento=prog.id_programacion_evento,
        id_contacto=contacto.id_contacto,
    )

    async with session_factory() as session:
        qr = await session.scalar(
            select(ParticipanteQr).where(
                ParticipanteQr.id_evento_contacto == id_ec
            )
        )
        assert qr is not None
        codigo = qr.codigo_seguro

    primera = await client.post(
        f"/api/v1/participantes/qr/{codigo}/imprimir", headers=headers
    )
    assert primera.status_code == 200, primera.text
    assert primera.json()["asistencia_evento"] is True
    assert primera.json()["credencial_impresa"] is True

    segunda = await client.post(
        f"/api/v1/participantes/qr/{codigo}/imprimir", headers=headers
    )
    assert segunda.status_code == 409, segunda.text


async def test_asignar_y_remover_beneficio_actualiza_requiere_coordinacion(
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
            session, empresa=ctx["empresa"], actor=ctx["actor"], sequence=38_001
        )
        beneficio_real = Beneficio(nombre="Beneficio Real 38001", estado=True)
        session.add(beneficio_real)
        await session.flush()
        session.add(
            DetallePoliticaEvento(
                id_politica_evento=ctx["politica"].id_politica_evento,
                id_beneficio=beneficio_real.id_beneficio,
                id_categoria=ctx["categoria"].id_categoria,
                entradas_gratuitas=5,
            )
        )
        await session.commit()

    headers = ctx["headers"]
    id_ec = await _agregar_contacto(
        client,
        headers,
        id_programacion_evento=prog.id_programacion_evento,
        id_contacto=contacto.id_contacto,
    )

    asignado = await client.post(
        "/api/v1/participantes/beneficios/asignar",
        headers=headers,
        json={"ids_evento_contacto": [id_ec], "id_beneficio": beneficio_real.id_beneficio},
    )
    assert asignado.status_code == 201, asignado.text
    assert asignado.json()[0]["requiere_coordinacion"] is False

    removido = await client.delete(
        f"/api/v1/participantes/evento-contactos/{id_ec}/beneficio", headers=headers
    )
    assert removido.status_code == 200, removido.text
    assert removido.json()["requiere_coordinacion"] is True


async def test_asignar_sin_beneficio_no_borra_requiere_coordinacion(
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
            session, empresa=ctx["empresa"], actor=ctx["actor"], sequence=39_001
        )
        await session.commit()

    headers = ctx["headers"]
    id_ec = await _agregar_contacto(
        client,
        headers,
        id_programacion_evento=prog.id_programacion_evento,
        id_contacto=contacto.id_contacto,
    )

    asignado = await client.post(
        "/api/v1/participantes/beneficios/asignar",
        headers=headers,
        json={"ids_evento_contacto": [id_ec], "id_beneficio": ctx["beneficio"].id_beneficio},
    )
    assert asignado.status_code == 201, asignado.text
    assert asignado.json()[0]["requiere_coordinacion"] is True


async def test_no_asigna_beneficio_a_programacion_no_abierta(
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
            session, empresa=ctx["empresa"], actor=ctx["actor"], sequence=39_201
        )
        await session.commit()

    headers = ctx["headers"]
    id_ec = await _agregar_contacto(
        client,
        headers,
        id_programacion_evento=prog.id_programacion_evento,
        id_contacto=contacto.id_contacto,
    )

    async with session_factory() as session:
        prog_row = await session.get(
            ProgramacionEvento, prog.id_programacion_evento
        )
        prog_row.estado = EventoEstado.FINALIZADO
        await session.commit()

    response = await client.post(
        "/api/v1/participantes/beneficios/asignar",
        headers=headers,
        json={"ids_evento_contacto": [id_ec], "id_beneficio": ctx["beneficio"].id_beneficio},
    )
    assert response.status_code == 409, response.text


async def test_sin_beneficio_no_aparece_en_disponibles(
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
            session, empresa=ctx["empresa"], actor=ctx["actor"], sequence=39_101
        )
        await session.commit()

    headers = ctx["headers"]
    id_ec = await _agregar_contacto(
        client,
        headers,
        id_programacion_evento=prog.id_programacion_evento,
        id_contacto=contacto.id_contacto,
    )

    disponibles = await client.get(
        f"/api/v1/participantes/evento-contactos/{id_ec}/beneficios-disponibles",
        headers=headers,
    )
    assert disponibles.status_code == 200, disponibles.text
    ids = [item["id_beneficio"] for item in disponibles.json()]
    assert ctx["beneficio"].id_beneficio not in ids


async def test_reimpresion_requiere_password_correcta_del_responsable(
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
            session, empresa=ctx["empresa"], actor=ctx["actor"], sequence=36_001
        )
        responsable = await crear_responsable(
            session, programacion=prog, usuario=ctx["actor"]
        )
        await session.commit()

    headers = ctx["headers"]
    id_ec = await _agregar_contacto(
        client,
        headers,
        id_programacion_evento=prog.id_programacion_evento,
        id_contacto=contacto.id_contacto,
    )

    async with session_factory() as session:
        qr = await session.scalar(
            select(ParticipanteQr).where(
                ParticipanteQr.id_evento_contacto == id_ec
            )
        )
        codigo = qr.codigo_seguro

    await client.post(f"/api/v1/participantes/qr/{codigo}/imprimir", headers=headers)

    incorrecta = await client.post(
        f"/api/v1/participantes/evento-contactos/{id_ec}/reimprimir",
        headers=headers,
        json={
            "id_responsable_evento": responsable.id_responsable_evento,
            "password": "clave-incorrecta",
        },
    )
    assert incorrecta.status_code == 403, incorrecta.text

    correcta = await client.post(
        f"/api/v1/participantes/evento-contactos/{id_ec}/reimprimir",
        headers=headers,
        json={
            "id_responsable_evento": responsable.id_responsable_evento,
            "password": VALID_PASSWORD,
        },
    )
    assert correcta.status_code == 200, correcta.text

    async with session_factory() as session:
        auditoria = await session.scalar(
            select(Auditoria).where(Auditoria.accion == "REIMPRESION_CREDENCIAL")
        )
        assert auditoria is not None
        assert auditoria.id_entidad == str(id_ec)
