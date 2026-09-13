# SPDX-License-Identifier: GPL-3.0-or-later
#
# Theme data bindings.
#
# Theme strings such as "{summary.running_vms}" or "{guest.cpu_percent:.0f}%"
# are resolved against the context built by models.build_context(). Python's
# format string syntax is used directly, which gives access to dotted attributes,
# list indexing ({servers[0].name}) and dict lookup ({server[pve-main].status}).

import re
import string
from typing import Any, Mapping

from proxmox_status_screen.log import logger

_FIELD_ONLY = re.compile(r"^\s*\{([^{}]+)\}\s*$")
_FORMATTER = string.Formatter()


def render_binding(template: Any, context: Mapping[str, Any]) -> str:
    """Render a template string against the context. Never raises."""
    if template is None:
        return ""
    if not isinstance(template, str):
        return str(template)

    try:
        return template.format_map(context)
    except (KeyError, AttributeError, IndexError, ValueError, TypeError) as exc:
        logger.debug("Binding %r could not be resolved: %s", template, exc)
        return ""


def resolve_value(template: Any, context: Mapping[str, Any]) -> Any:
    """Return the raw value behind a single-field binding, or the rendered string.

    Used for numeric widgets (graphs) where a formatted string would lose precision.
    """
    if not isinstance(template, str):
        return template

    match = _FIELD_ONLY.match(template)
    if not match:
        return render_binding(template, context)

    field_name = match.group(1).split("!", 1)[0].split(":", 1)[0].strip()
    try:
        value, _ = _FORMATTER.get_field(field_name, (), context)
        return value
    except (KeyError, AttributeError, IndexError, ValueError) as exc:
        logger.debug("Binding %r could not be resolved: %s", template, exc)
        return None


def resolve_number(
    template: Any, context: Mapping[str, Any], default: float = float("nan")
) -> float:
    """Resolve a binding to a float, or ``default`` if it is not numeric."""
    value = resolve_value(template, context)
    if value is None:
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace("%", "").strip())
    except ValueError:
        return default
