from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.comunicaciones.models import (
    CorreoPlantilla,
    CorreoPlantillaHistorial,
)
from app.modules.comunicaciones.template_catalog import PLANTILLAS_BASE


async def seed_default_templates(
    bind: AsyncSession,
) -> None:
    """Crea las plantillas iniciales sin sobrescribir personalizaciones."""
    for base in PLANTILLAS_BASE:
        plantilla = await bind.scalar(
            select(CorreoPlantilla).where(CorreoPlantilla.codigo == base.codigo)
        )
        if plantilla is not None:
            continue

        plantilla = CorreoPlantilla(
            codigo=base.codigo,
            nombre=base.nombre,
            asunto=base.asunto,
            cuerpo_html=base.cuerpo_html,
            cuerpo_texto=base.cuerpo_texto,
            variables_permitidas=list(base.variables_permitidas),
            version_actual=1,
            estado=True,
        )
        bind.add(plantilla)
        await bind.flush()
        bind.add(
            CorreoPlantillaHistorial(
                id_plantilla=plantilla.id_plantilla,
                version=1,
                asunto=plantilla.asunto,
                cuerpo_html=plantilla.cuerpo_html,
                cuerpo_texto=plantilla.cuerpo_texto,
                motivo="Plantilla inicial del sistema",
            )
        )
    await bind.flush()
