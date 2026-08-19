from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import settings


@dataclass
class RucInfo:
    ruc: str
    razon_social: str
    tipo_contribuyente: str | None = None
    estado: str | None = None
    condicion: str | None = None
    direccion: str | None = None


class RucConsultaError(Exception):
    pass


class RucNoEncontradoError(RucConsultaError):
    pass


class RucConsultor(Protocol):
    async def consultar(self, ruc: str) -> RucInfo: ...


class FactilizaRucConsultor:
    def __init__(
        self, *, base_url: str, token: str, timeout_seconds: float = 15.0
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds

    async def consultar(self, ruc: str) -> RucInfo:
        url = f"{self.base_url}/ruc/info/{ruc}"
        headers = {"Authorization": f"Bearer {self.token}"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise RucConsultaError("No se pudo conectar con el servicio de RUC.") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise RucConsultaError("Respuesta inválida del servicio de RUC.") from exc

        if response.status_code != 200 or not body.get("success"):
            raise RucNoEncontradoError("RUC no encontrado o inválido.")

        data = body.get("data") or {}
        return RucInfo(
            ruc=str(data.get("numero", ruc)),
            razon_social=data.get("nombre_o_razon_social", ""),
            tipo_contribuyente=data.get("tipo_contribuyente"),
            estado=data.get("estado"),
            condicion=data.get("condicion"),
            direccion=data.get("direccion_completa") or data.get("direccion"),
        )


def get_ruc_consultor() -> RucConsultor:
    return FactilizaRucConsultor(
        base_url=settings.factiliza_base_url,
        token=settings.factiliza_api_token.get_secret_value(),
    )
