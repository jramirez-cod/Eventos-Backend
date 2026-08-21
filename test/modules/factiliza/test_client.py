import httpx
import pytest

from app.modules.factiliza.client import (
    FactilizaClient,
    FactilizaDocumentNotFoundError,
    FactilizaInvalidResponseError,
    FactilizaUnavailableError,
)


pytestmark = pytest.mark.asyncio


async def _client_with_response(
    response: httpx.Response,
    *,
    expected_path: str | None = None,
) -> tuple[FactilizaClient, httpx.AsyncClient]:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-token"
        assert request.headers["Accept"] == "application/json"
        if expected_path is not None:
            assert request.url.path == expected_path
        return response

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return (
        FactilizaClient(
            base_url="https://api.factiliza.com/v1/",
            token="test-token",
            http_client=http_client,
        ),
        http_client,
    )


async def test_consultar_ruc_mapea_respuesta_completa() -> None:
    response = httpx.Response(
        200,
        json={
            "status": 200,
            "success": True,
            "message": "Exito",
            "data": {
                "numero": "20552103816",
                "nombre_o_razon_social": "AGROLIGHT PERU S.A.C.",
                "tipo_contribuyente": "SOCIEDAD ANONIMA CERRADA",
                "estado": "ACTIVO",
                "condicion": "HABIDO",
                "departamento": "LIMA",
                "provincia": "LIMA",
                "distrito": "SANTA ANITA",
                "direccion": "PJ. JORGE BASADRE 158",
                "direccion_completa": "PJ. JORGE BASADRE 158, LIMA",
                "ubigeo_sunat": "150137",
                "ubigeo": ["15", "1501", "150137"],
            },
        },
    )
    client, http_client = await _client_with_response(
        response, expected_path="/v1/ruc/info/20552103816"
    )
    try:
        result = await client.consultar_ruc("20552103816")
    finally:
        await http_client.aclose()

    assert result.numero == "20552103816"
    assert result.nombre_o_razon_social == "AGROLIGHT PERU S.A.C."
    assert result.ubigeo == ["15", "1501", "150137"]


async def test_consultar_dni_mapea_respuesta() -> None:
    response = httpx.Response(
        200,
        json={
            "status": 200,
            "success": True,
            "message": "Exito",
            "data": {
                "numero": "27427864",
                "nombres": "JOSE PEDRO",
                "apellido_paterno": "CASTILLO",
                "apellido_materno": "TERRONES",
                "nombre_completo": "CASTILLO TERRONES, JOSE PEDRO",
                "departamento": "CAJAMARCA",
                "provincia": "CHOTA",
                "distrito": "TACABAMBA",
                "direccion": "CASERIO PUNA",
                "direccion_completa": "CASERIO PUNA, CAJAMARCA",
                "ubigeo_reniec": "060615",
                "ubigeo_sunat": "060417",
                "ubigeo": ["06", "0604", "060417"],
                "fecha_nacimiento": "",
                "sexo": "",
            },
        },
    )
    client, http_client = await _client_with_response(
        response, expected_path="/v1/dni/info/27427864"
    )
    try:
        result = await client.consultar_dni("27427864")
    finally:
        await http_client.aclose()

    assert result.nombres == "JOSE PEDRO"
    assert result.apellido_paterno == "CASTILLO"
    assert result.ubigeo_reniec == "060615"


async def test_consultar_carnet_acepta_envelope_sin_success() -> None:
    response = httpx.Response(
        200,
        json={
            "status": 200,
            "message": "Exito",
            "data": {
                "numero": "001077238",
                "nombres": "ARCILA",
                "apellido_paterno": "LUZ CELIA KORINA",
                "apellido_materno": "RIVADENEIRA",
            },
        },
    )
    client, http_client = await _client_with_response(
        response, expected_path="/v1/cee/info/001077238"
    )
    try:
        result = await client.consultar_carnet_extranjeria("001077238")
    finally:
        await http_client.aclose()

    assert result.numero == "001077238"
    assert result.apellido_materno == "RIVADENEIRA"


@pytest.mark.parametrize("status_code", [400, 404])
async def test_documento_no_encontrado(status_code: int) -> None:
    response = httpx.Response(
        status_code,
        json={"status": status_code, "success": False, "message": "Bad Request"},
    )
    client, http_client = await _client_with_response(response)
    try:
        with pytest.raises(FactilizaDocumentNotFoundError):
            await client.consultar_dni("27427864")
    finally:
        await http_client.aclose()


@pytest.mark.parametrize("status_code", [401, 403, 429, 500, 503])
async def test_error_de_credenciales_o_disponibilidad(status_code: int) -> None:
    response = httpx.Response(
        status_code,
        json={"status": status_code, "success": False, "message": "Error"},
    )
    client, http_client = await _client_with_response(response)
    try:
        with pytest.raises(FactilizaUnavailableError):
            await client.consultar_ruc("20552103816")
    finally:
        await http_client.aclose()


async def test_token_no_configurado_falla_sin_llamar_a_la_red() -> None:
    llamado = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal llamado
        llamado = True
        return httpx.Response(200, json={})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = FactilizaClient(
        base_url="https://api.factiliza.com/v1",
        token="",
        http_client=http_client,
    )
    try:
        with pytest.raises(FactilizaUnavailableError):
            await client.consultar_ruc("20552103816")
    finally:
        await http_client.aclose()

    assert llamado is False


async def test_json_invalido_se_clasifica_como_respuesta_invalida() -> None:
    client, http_client = await _client_with_response(
        httpx.Response(200, text="<html>error</html>")
    )
    try:
        with pytest.raises(FactilizaInvalidResponseError):
            await client.consultar_ruc("20552103816")
    finally:
        await http_client.aclose()


async def test_error_de_conexion_se_clasifica_como_no_disponible() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin conexion", request=request)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = FactilizaClient(
        base_url="https://api.factiliza.com/v1",
        token="test-token",
        http_client=http_client,
    )
    try:
        with pytest.raises(FactilizaUnavailableError):
            await client.consultar_ruc("20552103816")
    finally:
        await http_client.aclose()
