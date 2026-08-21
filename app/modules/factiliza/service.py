from app.modules.factiliza.client import FactilizaGateway
from app.modules.factiliza.dto import (
    CarnetExtranjeriaResponseDTO,
    DniResponseDTO,
    RucResponseDTO,
)


class FactilizaService:
    def __init__(self, gateway: FactilizaGateway) -> None:
        self.gateway = gateway

    async def consultar_ruc(self, ruc: str) -> RucResponseDTO:
        return await self.gateway.consultar_ruc(ruc)

    async def consultar_dni(self, dni: str) -> DniResponseDTO:
        return await self.gateway.consultar_dni(dni)

    async def consultar_carnet_extranjeria(
        self, carnet: str
    ) -> CarnetExtranjeriaResponseDTO:
        return await self.gateway.consultar_carnet_extranjeria(carnet)
