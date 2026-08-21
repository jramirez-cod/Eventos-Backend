from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.modules.factiliza.client import (
    FactilizaDocumentNotFoundError,
    FactilizaError,
    FactilizaGateway,
    get_factiliza_gateway,
)
from app.modules.factiliza.dto import (
    CarnetExtranjeriaResponseDTO,
    DniResponseDTO,
    RucResponseDTO,
)
from app.modules.factiliza.service import FactilizaService
from app.modules.usuarios.dependencies import get_current_user
from app.modules.usuarios.models import Usuario


router = APIRouter(prefix="/factiliza", tags=["Factiliza"])


def _raise_http_error(exc: FactilizaError, document_name: str) -> None:
    if isinstance(exc, FactilizaDocumentNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{document_name} no encontrado.",
        )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="No se pudo consultar Factiliza en este momento.",
    )


@router.get("/ruc/{ruc}", response_model=RucResponseDTO)
async def consultar_ruc(
    ruc: Annotated[str, Path(pattern=r"^\d{11}$")],
    actor: Usuario = Depends(get_current_user),
    gateway: FactilizaGateway = Depends(get_factiliza_gateway),
) -> RucResponseDTO:
    try:
        return await FactilizaService(gateway).consultar_ruc(ruc)
    except FactilizaError as exc:
        _raise_http_error(exc, "RUC")
        raise


@router.get("/dni/{dni}", response_model=DniResponseDTO)
async def consultar_dni(
    dni: Annotated[str, Path(pattern=r"^\d{8}$")],
    actor: Usuario = Depends(get_current_user),
    gateway: FactilizaGateway = Depends(get_factiliza_gateway),
) -> DniResponseDTO:
    try:
        return await FactilizaService(gateway).consultar_dni(dni)
    except FactilizaError as exc:
        _raise_http_error(exc, "DNI")
        raise


@router.get(
    "/carnet-extranjeria/{carnet}",
    response_model=CarnetExtranjeriaResponseDTO,
)
async def consultar_carnet_extranjeria(
    carnet: Annotated[str, Path(pattern=r"^[A-Za-z0-9]{1,20}$")],
    actor: Usuario = Depends(get_current_user),
    gateway: FactilizaGateway = Depends(get_factiliza_gateway),
) -> CarnetExtranjeriaResponseDTO:
    carnet_normalizado = carnet.upper()
    try:
        return await FactilizaService(gateway).consultar_carnet_extranjeria(
            carnet_normalizado
        )
    except FactilizaError as exc:
        _raise_http_error(exc, "Carne de extranjeria")
        raise
