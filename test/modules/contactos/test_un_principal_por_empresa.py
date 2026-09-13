"""A lo sumo un contacto principal por empresa, garantizado por la BD.

La lógica del servicio ya demota al anterior; este test prueba que aunque se
salte esa lógica (concurrencia, script, SQL directo) la base lo impide.
"""
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.modules.contactos.models import Contacto
from test.modules.contactos.conftest import create_contacto, create_empresa
from test.modules.usuarios.conftest import create_role, create_user


pytestmark = pytest.mark.asyncio


async def test_la_bd_rechaza_dos_principales_en_la_misma_empresa(session_factory) -> None:
    async with session_factory() as session:
        role = await create_role(session, "Rol principal unico")
        actor = await create_user(session, role, username="actor.principal.unico")
        empresa = await create_empresa(session, sequence=70_001)
        primero = await create_contacto(session, empresa=empresa, actor=actor, sequence=70_001)
        segundo = await create_contacto(session, empresa=empresa, actor=actor, sequence=70_002)
        primero.es_contacto_principal = True
        segundo.es_contacto_principal = False
        await session.commit()
        id_empresa = empresa.id_empresa
        id_segundo = segundo.id_contacto

    async with session_factory() as session:
        segundo = await session.get(Contacto, id_segundo)
        assert segundo is not None
        segundo.es_contacto_principal = True  # sin demotar al primero
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async with session_factory() as session:
        principales = await session.scalar(
            select(func.count()).select_from(Contacto).where(
                Contacto.id_empresa == id_empresa,
                Contacto.es_contacto_principal.is_(True),
            )
        )
        assert principales == 1


async def test_el_servicio_sigue_pudiendo_cambiar_el_principal(client, session_factory) -> None:
    """Promover a otro contacto por la API debe seguir funcionando con el índice."""
    from test.modules.usuarios.conftest import auth_header, grant_permission

    async with session_factory() as session:
        role = await create_role(session, "Rol cambia principal")
        for permiso in ("CREAR_CONTACTO", "ACTUALIZAR_CONTACTO", "CONSULTAR_CONTACTO"):
            await grant_permission(session, role, permiso_nombre=permiso, modulo_nombre="CONTACTOS")
        actor = await create_user(session, role, username="actor.cambia.principal")
        empresa = await create_empresa(session, sequence=70_003)
        primero = await create_contacto(session, empresa=empresa, actor=actor, sequence=70_003)
        segundo = await create_contacto(session, empresa=empresa, actor=actor, sequence=70_004)
        primero.es_contacto_principal = True
        segundo.es_contacto_principal = False
        await session.commit()
        headers = auth_header(actor)
        id_empresa, id_primero, id_segundo = empresa.id_empresa, primero.id_contacto, segundo.id_contacto

    respuesta = await client.patch(
        f"/api/v1/contactos/{id_segundo}", headers=headers, json={"es_contacto_principal": True}
    )
    assert respuesta.status_code == 200, respuesta.text

    async with session_factory() as session:
        p1 = await session.get(Contacto, id_primero)
        p2 = await session.get(Contacto, id_segundo)
        assert p1 is not None and p2 is not None
        assert p1.es_contacto_principal is False
        assert p2.es_contacto_principal is True
        total = await session.scalar(
            select(func.count()).select_from(Contacto).where(
                Contacto.id_empresa == id_empresa, Contacto.es_contacto_principal.is_(True)
            )
        )
        assert total == 1
