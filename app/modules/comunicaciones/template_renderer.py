from html.parser import HTMLParser
import re
from typing import Any

from jinja2 import StrictUndefined, meta
from jinja2.sandbox import SandboxedEnvironment


_DANGEROUS_TAGS = {
    "applet",
    "base",
    "embed",
    "form",
    "frame",
    "frameset",
    "iframe",
    "link",
    "object",
    "script",
}
_DANGEROUS_URL = re.compile(r"^\s*(?:javascript|data\s*:\s*text/html)", re.I)
_DANGEROUS_CSS = re.compile(r"(?:expression\s*\(|javascript\s*:)", re.I)


class TemplateValidationError(ValueError):
    pass


class _EmailHtmlValidator(HTMLParser):
    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        lowered_tag = tag.lower()
        if lowered_tag in _DANGEROUS_TAGS:
            raise TemplateValidationError(
                f"La etiqueta HTML <{lowered_tag}> no está permitida."
            )
        for name, value in attrs:
            lowered_name = name.lower()
            normalized_value = value or ""
            if lowered_name.startswith("on"):
                raise TemplateValidationError(
                    f"El atributo HTML {lowered_name} no está permitido."
                )
            if lowered_name in {"href", "src", "action", "formaction"} and (
                _DANGEROUS_URL.search(normalized_value)
            ):
                raise TemplateValidationError("La URL HTML indicada no es segura.")
            if lowered_name == "style" and _DANGEROUS_CSS.search(normalized_value):
                raise TemplateValidationError("El estilo HTML indicado no es seguro.")


class CorreoTemplateRenderer:
    def __init__(self) -> None:
        self.environment = SandboxedEnvironment(
            autoescape=True,
            undefined=StrictUndefined,
        )

    def validate(
        self,
        *,
        asunto: str,
        cuerpo_html: str,
        cuerpo_texto: str,
        variables_permitidas: list[str],
    ) -> None:
        if "\r" in asunto or "\n" in asunto:
            raise TemplateValidationError(
                "El asunto no puede contener saltos de línea."
            )
        for value in (asunto, cuerpo_html, cuerpo_texto):
            if "{%" in value or "{#" in value:
                raise TemplateValidationError(
                    "Solo se permiten variables {{ ... }}; no se permiten bloques Jinja."
                )
            try:
                parsed = self.environment.parse(value)
            except Exception as exc:
                raise TemplateValidationError("La sintaxis de la plantilla es inválida.") from exc
            used = meta.find_undeclared_variables(parsed)
            unknown = sorted(used - set(variables_permitidas))
            if unknown:
                raise TemplateValidationError(
                    "Variables no permitidas: " + ", ".join(unknown)
                )
        parser = _EmailHtmlValidator(convert_charrefs=True)
        try:
            parser.feed(cuerpo_html)
            parser.close()
        except TemplateValidationError:
            raise
        except Exception as exc:
            raise TemplateValidationError("El cuerpo HTML es inválido.") from exc

    def render(
        self,
        *,
        asunto: str,
        cuerpo_html: str,
        cuerpo_texto: str,
        variables_permitidas: list[str],
        contexto: dict[str, Any],
    ) -> tuple[str, str, str]:
        self.validate(
            asunto=asunto,
            cuerpo_html=cuerpo_html,
            cuerpo_texto=cuerpo_texto,
            variables_permitidas=variables_permitidas,
        )
        unknown_context = sorted(set(contexto) - set(variables_permitidas))
        if unknown_context:
            raise TemplateValidationError(
                "El contexto contiene variables no permitidas: "
                + ", ".join(unknown_context)
            )
        try:
            return (
                self.environment.from_string(asunto).render(**contexto),
                self.environment.from_string(cuerpo_html).render(**contexto),
                self.environment.from_string(cuerpo_texto).render(**contexto),
            )
        except Exception as exc:
            raise TemplateValidationError(
                "No se pudo renderizar la plantilla; revise las variables requeridas."
            ) from exc
