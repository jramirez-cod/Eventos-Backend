import pytest

from app.modules.empresas import service as empresa_service_module
from app.modules.empresas.ruc_client import RucInfo
from test.modules.empresas.conftest import FakeRucConsultor
from test.modules.usuarios.conftest import auth_header, create_role, create_user, grant_permission


pytestmark = pytest.mark.asyncio


async def _actor_con_permisos(session, *, permisos):
    rol = await create_role(session, "ActorConsultaRuc")
    for permiso in permisos:
        await grant_permission(
            session, rol, permiso_nombre=permiso, modulo_nombre="EMPRESAS"
        )
    actor = await create_user(session, rol, username="actor.consulta.ruc")
    await session.commit()
    return actor


async def test_ruc_encontrado_no_llama_a_la_red_real(
    client, session_factory, monkeypatch
) -> None:
    fake = FakeRucConsultor(
        {
            "20552103816": RucInfo(
                ruc="20552103816",
                razon_social="AGROLIGHT PERU S.A.C.",
                tipo_contribuyente="SOCIEDAD ANONIMA CERRADA",
                estado="ACTIVO",
                condicion="HABIDO",
                direccion="PJ. JORGE BASADRE NRO. 158",
            )
        }
    )
    monkeypatch.setattr(
        empresa_service_module, "get_ruc_consultor", lambda: fake
    )

    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["CREAR_EMPRESA"])
        headers = auth_header(actor)

    response = await client.get(
        "/api/v1/empresas/consultar-ruc/20552103816", headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["razon_social"] == "AGROLIGHT PERU S.A.C."
    assert fake.llamadas == ["20552103816"]


async def test_ruc_no_encontrado_recibe_404(
    client, session_factory, monkeypatch
) -> None:
    fake = FakeRucConsultor({})
    monkeypatch.setattr(
        empresa_service_module, "get_ruc_consultor", lambda: fake
    )

    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["CREAR_EMPRESA"])
        headers = auth_header(actor)

    response = await client.get(
        "/api/v1/empresas/consultar-ruc/20000000000", headers=headers
    )

    assert response.status_code == 404
    assert fake.llamadas == ["20000000000"]


async def test_ruc_con_formato_invalido_recibe_422_sin_llamar_al_consultor(
    client, session_factory, monkeypatch
) -> None:
    fake = FakeRucConsultor({})
    monkeypatch.setattr(
        empresa_service_module, "get_ruc_consultor", lambda: fake
    )

    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["CREAR_EMPRESA"])
        headers = auth_header(actor)

    response = await client.get(
        "/api/v1/empresas/consultar-ruc/123", headers=headers
    )

    assert response.status_code == 422
    assert fake.llamadas == []
