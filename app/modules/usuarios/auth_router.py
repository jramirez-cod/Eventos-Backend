from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.usuarios.dependencies import oauth2_scheme
from app.modules.usuarios.dto import (
    CambioPasswordInicialRequestDTO,
    LoginRequestDTO,
    LoginResponseDTO,
    OAuthTokenResponseDTO,
    RecuperarPasswordRequestDTO,
    RecuperarPasswordResponseDTO,
    RestablecerPasswordRequestDTO,
)
from app.modules.usuarios.auth_service import (
    AuthService,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidPasswordChangeTokenError,
    InvalidRecoveryTokenError,
    PasswordMismatchError,
    PasswordPolicyViolationError,
)


router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/login", response_model=LoginResponseDTO)
async def login(
    data: LoginRequestDTO,
    db: AsyncSession = Depends(get_db),
) -> LoginResponseDTO:
    try:
        return await AuthService(db).login(data)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas.",
        )
    except InactiveUserError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inactivo.",
        )


@router.post("/token", response_model=OAuthTokenResponseDTO, include_in_schema=False)
async def token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> OAuthTokenResponseDTO:
    try:
        response = await AuthService(db).login(
            LoginRequestDTO(
                nombre_usuario=form_data.username,
                password=form_data.password,
            )
        )
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InactiveUserError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inactivo.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if response.debe_cambiar_password or not response.access_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Debe cambiar la contraseña inicial usando "
                "POST /api/v1/auth/login y luego "
                "POST /api/v1/auth/cambiar-password-inicial."
            ),
        )

    return OAuthTokenResponseDTO(access_token=response.access_token)


@router.post("/cambiar-password-inicial", response_model=LoginResponseDTO)
async def cambiar_password_inicial(
    data: CambioPasswordInicialRequestDTO,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> LoginResponseDTO:
    try:
        return await AuthService(db).cambiar_password_inicial(token=token, data=data)
    except InvalidPasswordChangeTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido para cambio de contraseña inicial.",
        )
    except PasswordMismatchError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Las contraseñas no coinciden.",
        )
    except PasswordPolicyViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.errors,
        )


@router.post("/recuperar-password", response_model=RecuperarPasswordResponseDTO)
async def recuperar_password(
    data: RecuperarPasswordRequestDTO,
    db: AsyncSession = Depends(get_db),
) -> RecuperarPasswordResponseDTO:
    return await AuthService(db).solicitar_recuperacion(data)


@router.post("/restablecer-password", response_model=LoginResponseDTO)
async def restablecer_password(
    data: RestablecerPasswordRequestDTO,
    db: AsyncSession = Depends(get_db),
) -> LoginResponseDTO:
    try:
        return await AuthService(db).restablecer_password(data)
    except InvalidRecoveryTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido.",
        )
    except PasswordMismatchError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Las contraseñas no coinciden.",
        )
    except PasswordPolicyViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.errors,
        )
