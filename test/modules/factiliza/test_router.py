from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from app.modules.factiliza.client import (
    FactilizaDocumentNotFoundError,
    FactilizaUnavailableError,
    get_factiliza_gateway,
)
from app.modules.factiliza.dto import (
    CarnetExtranjeriaResponseDTO,
    DniResponseDTO,
    RucResponseDTO,
)
from app.modules.factiliza.router import router
from app.modules.usuarios.dependencies import get_current_user
from test.modules.factiliza.conftest import FakeFactilizaGateway


pytestmark = pytest.mark.asyncio


async def _request(fake: FakeFactilizaGateway, path: str):
    async def override_current_user():
        return object()

    async def override_gateway():
        return fake

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_factiliza_gateway] = override_gateway
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get(path)


async def test_endpoints_devuelven_ruc_dni_y_carnet() -> None:
    fake = FakeFactilizaGateway(
        ruc_result=RucResponseDTO(
            numero="20552103816",
            nombre_o_razon_social="AGROLIGHT PERU S.A.C.",
        ),
        dni_result=DniResponseDTO(
            numero="27427864",
            nombres="JOSE PEDRO",
            apellido_paterno="CASTILLO",
            apellido_materno="TERRONES",
        ),
        carnet_result=CarnetExtranjeriaResponseDTO(
            numero="001077238",
            nombres="ARCILA",
            apellido_paterno="LUZ CELIA KORINA",
            apellido_materno="RIVADENEIRA",
        ),
    )

    ruc = await _request(fake, "/api/v1/factiliza/ruc/20552103816")
    dni = await _request(fake, "/api/v1/factiliza/dni/27427864")
    carnet = await _request(
        fake, "/api/v1/factiliza/carnet-extranjeria/001077238"
    )

    assert ruc.status_code == 200
    assert ruc.json()["nombre_o_razon_social"] == "AGROLIGHT PERU S.A.C."
    assert dni.status_code == 200
    assert dni.json()["apellido_paterno"] == "CASTILLO"
    assert carnet.status_code == 200
    assert carnet.json()["numero"] == "001077238"
    assert fake.llamadas == [
        ("ruc", "20552103816"),
        ("dni", "27427864"),
        ("carnet", "001077238"),
    ]


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/factiliza/ruc/123",
        "/api/v1/factiliza/dni/123",
        "/api/v1/factiliza/carnet-extranjeria/ABC-123",
    ],
)
async def test_formato_invalido_devuelve_422_sin_consultar(path: str) -> None:
    fake = FakeFactilizaGateway()

    response = await _request(fake, path)

    assert response.status_code == 422
    assert fake.llamadas == []


async def test_documento_no_encontrado_devuelve_404() -> None:
    fake = FakeFactilizaGateway(
        dni_result=FactilizaDocumentNotFoundError("No encontrado")
    )

    response = await _request(fake, "/api/v1/factiliza/dni/27427864")

    assert response.status_code == 404
    assert response.json() == {"detail": "DNI no encontrado."}


async def test_proveedor_no_disponible_devuelve_503_sin_filtrar_detalles() -> None:
    fake = FakeFactilizaGateway(
        ruc_result=FactilizaUnavailableError("token secreto invalido")
    )

    response = await _request(fake, "/api/v1/factiliza/ruc/20552103816")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "No se pudo consultar Factiliza en este momento."
    }


async def test_endpoint_requiere_access_token() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/factiliza/dni/27427864")

    assert response.status_code == 401
