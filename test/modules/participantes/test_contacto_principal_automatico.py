import pytest

from test.modules.contactos.conftest import create_contacto, create_empresa
from test.modules.participantes.conftest import (
    afiliar_empresa_http,
    create_programacion,
    seed_participante_actor,
)


pytestmark = pytest.mark.asyncio


async def test_afiliar_empresa_autocompleta_contacto_principal_existente(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_participante_actor(session)
        programacion = await create_programacion(session)
        empresa = await create_empresa(session, sequence=92_001)
        contacto = await create_contacto(
            session, empresa=empresa, actor=actor, sequence=92_001
        )
        contacto.es_contacto_principal = True
        await session.commit()
        id_contacto = contacto.id_contacto

    afiliacion = await afiliar_empresa_http(
        client, headers, programacion=programacion, empresa=empresa
    )

    assert afiliacion["id_contacto_principal"] == id_contacto


async def test_afiliar_empresa_sin_contacto_principal_deja_vacio(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_participante_actor(session)
        programacion = await create_programacion(session)
        empresa = await create_empresa(session, sequence=92_002)
        await create_contacto(session, empresa=empresa, actor=actor, sequence=92_002)
        await session.commit()

    afiliacion = await afiliar_empresa_http(
        client, headers, programacion=programacion, empresa=empresa
    )

    assert afiliacion["id_contacto_principal"] is None
