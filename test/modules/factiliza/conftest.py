from dataclasses import dataclass, field

from app.modules.factiliza.dto import (
    CarnetExtranjeriaResponseDTO,
    DniResponseDTO,
    RucResponseDTO,
)


@dataclass
class FakeFactilizaGateway:
    ruc_result: RucResponseDTO | Exception | None = None
    dni_result: DniResponseDTO | Exception | None = None
    carnet_result: CarnetExtranjeriaResponseDTO | Exception | None = None
    llamadas: list[tuple[str, str]] = field(default_factory=list)

    async def consultar_ruc(self, ruc: str) -> RucResponseDTO:
        self.llamadas.append(("ruc", ruc))
        return self._result(self.ruc_result)

    async def consultar_dni(self, dni: str) -> DniResponseDTO:
        self.llamadas.append(("dni", dni))
        return self._result(self.dni_result)

    async def consultar_carnet_extranjeria(
        self, carnet: str
    ) -> CarnetExtranjeriaResponseDTO:
        self.llamadas.append(("carnet", carnet))
        return self._result(self.carnet_result)

    @staticmethod
    def _result(value):
        if isinstance(value, Exception):
            raise value
        assert value is not None
        return value
