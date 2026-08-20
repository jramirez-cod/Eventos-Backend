import pytest
from sqlalchemy import delete, select

from app.modules.auditoria.models import Auditoria
from app.modules.contactos.models import Contacto, ContactoHistorialEmpresa
from test.modules.contactos.conftest import (
    create_contacto,
    create_empresa,
    seed_contact_actor,
)


pytestmark = pytest.mark.asyncio


async def test_cambiar_empresa_conserva_historial_y_una_sola_vigencia(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_contact_actor(session)
        origen = await create_empresa(session, sequence=10)
        destino = await create_empresa(session, sequence=11)
        contacto = await create_contacto(
            session, empresa=origen, actor=actor, sequence=10
        )
        await session.commit()
        id_contacto = contacto.id_contacto
        id_origen = origen.id_empresa
        id_destino = destino.id_empresa

    response = await client.patch(
        f"/api/v1/contactos/{id_contacto}/empresa",
        headers=headers,
        json={"id_empresa": id_destino, "motivo": "Cambio laboral"},
    )

    assert response.status_code == 200
    assert response.json()["id_empresa"] == id_destino

    async with session_factory() as session:
        stored = await session.get(Contacto, id_contacto)
        historiales = list(
            (
                await session.scalars(
                    select(ContactoHistorialEmpresa)
                    .where(ContactoHistorialEmpresa.id_contacto == id_contacto)
                    .order_by(ContactoHistorialEmpresa.fecha_inicio)
                )
            ).all()
        )
        auditoria = await session.scalar(
            select(Auditoria).where(
                Auditoria.accion == "CAMBIAR_EMPRESA_CONTACTO"
            )
        )

    assert stored is not None
    assert stored.id_empresa == id_destino
    assert len(historiales) == 2
    historial_origen = next(h for h in historiales if h.id_empresa == id_origen)
    historial_destino = next(h for h in historiales if h.id_empresa == id_destino)
    assert historial_origen.fecha_fin is not None
    assert historial_destino.fecha_fin is None
    assert sum(history.fecha_fin is None for history in historiales) == 1
    assert auditoria is not None
    assert auditoria.valor_anterior == {"id_empresa": id_origen}
    assert auditoria.valor_nuevo == {"id_empresa": id_destino}


async def test_cambiar_empresa_destino_inexistente_recibe_404(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_contact_actor(session)
        origen = await create_empresa(session, sequence=12)
        contacto = await create_contacto(
            session, empresa=origen, actor=actor, sequence=12
        )
        await session.commit()
        id_contacto = contacto.id_contacto

    response = await client.patch(
        f"/api/v1/contactos/{id_contacto}/empresa",
        headers=headers,
        json={"id_empresa": 999_999, "motivo": "Cambio laboral"},
    )
    assert response.status_code == 404


async def test_cambiar_empresa_destino_inactivo_recibe_400(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_contact_actor(session)
        origen = await create_empresa(session, sequence=13)
        destino = await create_empresa(session, sequence=14, estado=False)
        contacto = await create_contacto(
            session, empresa=origen, actor=actor, sequence=13
        )
        await session.commit()
        id_contacto = contacto.id_contacto
        id_destino = destino.id_empresa

    response = await client.patch(
        f"/api/v1/contactos/{id_contacto}/empresa",
        headers=headers,
        json={"id_empresa": id_destino, "motivo": "Cambio laboral"},
    )
    assert response.status_code == 400


async def test_cambiar_a_misma_empresa_recibe_409(client, session_factory) -> None:
    async with session_factory() as session:
        actor, headers = await seed_contact_actor(session)
        empresa = await create_empresa(session, sequence=15)
        contacto = await create_contacto(
            session, empresa=empresa, actor=actor, sequence=15
        )
        await session.commit()
        id_contacto = contacto.id_contacto
        id_empresa = empresa.id_empresa

    response = await client.patch(
        f"/api/v1/contactos/{id_contacto}/empresa",
        headers=headers,
        json={"id_empresa": id_empresa, "motivo": "Sin cambio"},
    )
    assert response.status_code == 409


async def test_cambiar_empresa_reconstruye_vigencia_inicial_si_no_existe(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_contact_actor(session)
        origen = await create_empresa(session, sequence=16)
        destino = await create_empresa(session, sequence=17)
        contacto = await create_contacto(
            session, empresa=origen, actor=actor, sequence=16
        )
        await session.execute(
            delete(ContactoHistorialEmpresa).where(
                ContactoHistorialEmpresa.id_contacto == contacto.id_contacto
            )
        )
        await session.commit()
        id_contacto = contacto.id_contacto
        id_origen = origen.id_empresa
        id_destino = destino.id_empresa

    response = await client.patch(
        f"/api/v1/contactos/{id_contacto}/empresa",
        headers=headers,
        json={"id_empresa": id_destino, "motivo": "Cambio laboral"},
    )
    assert response.status_code == 200

    async with session_factory() as session:
        histories = list(
            (
                await session.scalars(
                    select(ContactoHistorialEmpresa).where(
                        ContactoHistorialEmpresa.id_contacto == id_contacto
                    )
                )
            ).all()
        )

    assert len(histories) == 2
    previous = next(history for history in histories if history.id_empresa == id_origen)
    current = next(history for history in histories if history.id_empresa == id_destino)
    assert previous.fecha_fin is not None
    assert current.fecha_fin is None
