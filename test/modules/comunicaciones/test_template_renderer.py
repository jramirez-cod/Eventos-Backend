import pytest

from app.modules.comunicaciones.template_renderer import (
    CorreoTemplateRenderer,
    TemplateValidationError,
)


def test_renderiza_variables_permitidas_con_autoescape() -> None:
    renderer = CorreoTemplateRenderer()

    asunto, html, texto = renderer.render(
        asunto="Hola {{ nombre }}",
        cuerpo_html="<p>{{ nombre }}</p>",
        cuerpo_texto="Hola {{ nombre }}",
        variables_permitidas=["nombre"],
        contexto={"nombre": "<Admin>"},
    )

    assert asunto == "Hola &lt;Admin&gt;"
    assert html == "<p>&lt;Admin&gt;</p>"
    assert texto == "Hola &lt;Admin&gt;"


@pytest.mark.parametrize(
    "html",
    [
        "<script>alert(1)</script>",
        '<a href="javascript:alert(1)">Abrir</a>',
        '<img src="x" onerror="alert(1)">',
    ],
)
def test_rechaza_html_activo_peligroso(html: str) -> None:
    renderer = CorreoTemplateRenderer()

    with pytest.raises(TemplateValidationError):
        renderer.validate(
            asunto="Asunto",
            cuerpo_html=html,
            cuerpo_texto="Texto",
            variables_permitidas=[],
        )


def test_rechaza_variable_fuera_de_allowlist() -> None:
    renderer = CorreoTemplateRenderer()

    with pytest.raises(TemplateValidationError, match="no permitidas"):
        renderer.validate(
            asunto="Hola {{ secreto }}",
            cuerpo_html="<p>Hola</p>",
            cuerpo_texto="Hola",
            variables_permitidas=["nombre"],
        )


def test_rechaza_bloques_jinja() -> None:
    renderer = CorreoTemplateRenderer()

    with pytest.raises(TemplateValidationError, match="bloques Jinja"):
        renderer.validate(
            asunto="Asunto",
            cuerpo_html="{% include '/etc/passwd' %}",
            cuerpo_texto="Texto",
            variables_permitidas=[],
        )

