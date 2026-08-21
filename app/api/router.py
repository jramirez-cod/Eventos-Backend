from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.modules.categorias.router import router as categorias_router
from app.modules.contactos.router import router as contactos_router
from app.modules.empresas.router import router as empresas_router
from app.modules.factiliza.router import router as factiliza_router
from app.modules.grupos.router import router as grupos_router
from app.modules.maestros.router import router as maestros_router
from app.modules.usuarios.auth_router import router as auth_router
from app.modules.usuarios.router import router as usuarios_router

api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(usuarios_router)
api_router.include_router(grupos_router)
api_router.include_router(categorias_router)
api_router.include_router(empresas_router)
api_router.include_router(contactos_router)
api_router.include_router(factiliza_router)
api_router.include_router(maestros_router)
