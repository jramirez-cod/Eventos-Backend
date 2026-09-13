from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.comunicaciones.models import (
    CorreoPlantilla,
    CorreoPlantillaHistorial,
)
from app.modules.comunicaciones.template_catalog import (
    PLANTILLAS_BASE,
    PlantillaBase,
)


async def seed_default_templates(
    bind: AsyncSession,
) -> None:
    """Crea las plantillas iniciales sin sobrescribir personalizaciones."""
    for base in PLANTILLAS_BASE:
        plantilla = await bind.scalar(
            select(CorreoPlantilla).where(CorreoPlantilla.codigo == base.codigo)
        )
        if plantilla is not None:
            await _sincronizar_plantilla_existente(bind, plantilla, base)
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


async def _sincronizar_plantilla_existente(
    bind: AsyncSession,
    plantilla: CorreoPlantilla,
    base: PlantillaBase,
) -> None:
    """Alinea una plantilla ya sembrada con el catálogo, sin perder ediciones.

    Las variables permitidas se amplían siempre: son la lista blanca que valida
    el renderer, así que sin ellas una variable nueva del catálogo se rechazaría.
    El cuerpo solo se refresca si la plantilla nunca se editó desde el panel
    (editar incrementa `version_actual`), para no pisar personalizaciones.
    """
    permitidas = list(plantilla.variables_permitidas or [])
    faltantes = [v for v in base.variables_permitidas if v not in permitidas]
    if faltantes:
        plantilla.variables_permitidas = permitidas + faltantes

    if plantilla.version_actual != 1:
        return

    if (
        plantilla.asunto == base.asunto
        and plantilla.cuerpo_html == base.cuerpo_html
        and plantilla.cuerpo_texto == base.cuerpo_texto
    ):
        return

    plantilla.asunto = base.asunto
    plantilla.cuerpo_html = base.cuerpo_html
    plantilla.cuerpo_texto = base.cuerpo_texto
    historial = await bind.scalar(
        select(CorreoPlantillaHistorial).where(
            CorreoPlantillaHistorial.id_plantilla == plantilla.id_plantilla,
            CorreoPlantillaHistorial.version == 1,
        )
    )
    if historial is not None:
        historial.asunto = base.asunto
        historial.cuerpo_html = base.cuerpo_html
        historial.cuerpo_texto = base.cuerpo_texto
