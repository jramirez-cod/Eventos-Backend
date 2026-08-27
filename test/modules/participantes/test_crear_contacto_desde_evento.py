import pytest
from sqlalchemy import func, select

from app.modules.auditoria.models import Auditoria
from app.modules.contactos.models import Contacto, ContactoHistorialEmpresa
from app.modules.eventos.models import Evento, EventoEstado
from app.modules.participantes.models import EventoContacto
from app.modules.participantes.repository import ParticipanteRepository
from test.modules.participantes.conftest import (
    contacto_desde_evento_payload,
    evento_contacto_context,
)


pytestmark = pytest.mark.asyncio


async def test_crea_contacto_historial_evento_contacto_y_auditoria(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers, programacion, empresa, _, _ = await evento_contacto_context(
            session, client
        )
        payload = contacto_desde_evento_payload(actor=actor, empresa=empresa)

    response = await client.post(
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/evento-contactos/crear-contacto",
        headers=headers,
        json=payload,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id_empresa"] == empresa.id_empresa
    assert body["estado"] is True

    async with session_factory() as session:
        contacto = await session.get(Contacto, body["id_contacto"])
        assert contacto is not None
        assert contacto.id_empresa == empresa.id_empresa
        assert contacto.celular == "987654321"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ContactoHistorialEmpresa)
                .where(
                    ContactoHistorialEmpresa.id_contacto == contacto.id_contacto,
                    ContactoHistorialEmpresa.fecha_fin.is_(None),
                )
            )
            == 1
        )
        acciones = set(
            (
                await session.scalars(
                    select(Auditoria.accion).where(
                        Auditoria.accion.in_(
                            {"CREAR_CONTACTO", "CREAR_CONTACTO_DESDE_EVENTO"}
                        )
                    )
                )
            ).all()
        )
        assert acciones == {"CREAR_CONTACTO", "CREAR_CONTACTO_DESDE_EVENTO"}


@pytest.mark.parametrize("estado", [EventoEstado.FINALIZADO, EventoEstado.INACTIVO])
async def test_no_crea_contacto_desde_evento_no_abierto(
    client, session_factory, estado
) -> None:
    async with session_factory() as session:
        actor, headers, programacion, empresa, _, _ = await evento_contacto_context(
            session, client
        )
        payload = contacto_desde_evento_payload(actor=actor, empresa=empresa)

    async with session_factory() as session:
        evento = await session.get(Evento, programacion.id_evento)
        evento.estado = estado
        await session.commit()

    response = await client.post(
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/evento-contactos/crear-contacto",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 409


async def test_rollback_no_deja_contacto_si_falla_inscripcion(
    client, session_factory, monkeypatch
) -> None:
    async with session_factory() as session:
        actor, headers, programacion, empresa, _, _ = await evento_contacto_context(
            session, client
        )
        payload = contacto_desde_evento_payload(actor=actor, empresa=empresa)
        documento = payload["contacto"]["numero_documento"]

    async def fail_create(*args, **kwargs):
        raise RuntimeError("fallo forzado al inscribir")

    monkeypatch.setattr(
        ParticipanteRepository, "create_evento_contacto", fail_create
    )

    with pytest.raises(RuntimeError, match="fallo forzado"):
        await client.post(
            f"/api/v1/participantes/programaciones/"
            f"{programacion.id_programacion_evento}/evento-contactos/crear-contacto",
            headers=headers,
            json=payload,
        )

    async with session_factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Contacto)
                .where(Contacto.numero_documento == documento)
            )
            == 0
        )
        assert (
            await session.scalar(select(func.count()).select_from(EventoContacto))
            == 0
        )
