from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings
from app.modules.factiliza.client import (
    FactilizaClient,
    FactilizaDocumentNotFoundError,
    FactilizaError,
)


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
        self.client = FactilizaClient(
            base_url=base_url,
            token=token,
            timeout_seconds=timeout_seconds,
        )

    async def consultar(self, ruc: str) -> RucInfo:
        try:
            data = await self.client.consultar_ruc(ruc)
        except FactilizaDocumentNotFoundError as exc:
            raise RucNoEncontradoError("RUC no encontrado o invalido.") from exc
        except FactilizaError as exc:
            raise RucConsultaError(
                "No se pudo consultar el RUC en Factiliza."
            ) from exc

        return RucInfo(
            ruc=data.numero,
            razon_social=data.nombre_o_razon_social,
            tipo_contribuyente=data.tipo_contribuyente,
            estado=data.estado,
            condicion=data.condicion,
            direccion=data.direccion_completa or data.direccion,
        )


def get_ruc_consultor() -> RucConsultor:
    return FactilizaRucConsultor(
        base_url=settings.factiliza_base_url,
        token=settings.factiliza_api_token.get_secret_value(),
        timeout_seconds=settings.factiliza_timeout_seconds,
    )
