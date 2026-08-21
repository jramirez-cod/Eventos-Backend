from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.modules.factiliza.dto import (
    CarnetExtranjeriaResponseDTO,
    DniResponseDTO,
    RucResponseDTO,
)


ResponseDTO = TypeVar("ResponseDTO", bound=BaseModel)


class FactilizaError(Exception):
    """Error base de la integracion con Factiliza."""


class FactilizaDocumentNotFoundError(FactilizaError):
    pass


class FactilizaUnavailableError(FactilizaError):
    pass


class FactilizaInvalidResponseError(FactilizaError):
    pass


class FactilizaGateway(Protocol):
    async def consultar_ruc(self, ruc: str) -> RucResponseDTO: ...

    async def consultar_dni(self, dni: str) -> DniResponseDTO: ...

    async def consultar_carnet_extranjeria(
        self, carnet: str
    ) -> CarnetExtranjeriaResponseDTO: ...


class FactilizaClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_seconds: float = 15.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token.strip()
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client

    async def consultar_ruc(self, ruc: str) -> RucResponseDTO:
        return await self._consultar(
            path=f"/ruc/info/{ruc}",
            response_type=RucResponseDTO,
        )

    async def consultar_dni(self, dni: str) -> DniResponseDTO:
        return await self._consultar(
            path=f"/dni/info/{dni}",
            response_type=DniResponseDTO,
        )

    async def consultar_carnet_extranjeria(
        self, carnet: str
    ) -> CarnetExtranjeriaResponseDTO:
        return await self._consultar(
            path=f"/cee/info/{carnet}",
            response_type=CarnetExtranjeriaResponseDTO,
        )

    async def _consultar(
        self,
        *,
        path: str,
        response_type: type[ResponseDTO],
    ) -> ResponseDTO:
        if not self.token:
            raise FactilizaUnavailableError(
                "El token de Factiliza no esta configurado."
            )

        response = await self._get(path)
        body = self._read_body(response)

        if response.status_code in (401, 403, 429) or response.status_code >= 500:
            raise FactilizaUnavailableError(
                "Factiliza no esta disponible o rechazo sus credenciales."
            )
        if response.status_code in (400, 404) or body.get("success") is False:
            raise FactilizaDocumentNotFoundError(
                "El documento no fue encontrado por Factiliza."
            )
        if response.status_code != 200:
            raise FactilizaUnavailableError(
                "Factiliza devolvio un estado HTTP no esperado."
            )

        data = body.get("data")
        if not isinstance(data, dict):
            raise FactilizaInvalidResponseError(
                "Factiliza devolvio una respuesta sin datos validos."
            )

        try:
            return response_type.model_validate(data)
        except ValidationError as exc:
            raise FactilizaInvalidResponseError(
                "Factiliza devolvio datos con una estructura invalida."
            ) from exc

    async def _get(self, path: str) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }
        url = f"{self.base_url}{path}"

        try:
            if self.http_client is not None:
                return await self.http_client.get(url, headers=headers)

            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                return await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise FactilizaUnavailableError(
                "No se pudo conectar con Factiliza."
            ) from exc

    @staticmethod
    def _read_body(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise FactilizaInvalidResponseError(
                "Factiliza devolvio una respuesta que no es JSON."
            ) from exc

        if not isinstance(body, dict):
            raise FactilizaInvalidResponseError(
                "Factiliza devolvio una respuesta JSON invalida."
            )
        return body


def get_factiliza_gateway() -> FactilizaGateway:
    return FactilizaClient(
        base_url=settings.factiliza_base_url,
        token=settings.factiliza_api_token.get_secret_value(),
        timeout_seconds=settings.factiliza_timeout_seconds,
    )
