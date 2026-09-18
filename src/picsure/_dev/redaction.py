"""Classify a request body as participant-bearing, for dev-mode labelling.

:func:`body_is_sensitive` answers one question: does this request body
ask the backend for per-patient rows? The transport client calls it for
every request it records, and a ``True`` puts ``redacted:
"participant"`` in that event's metadata. Attaching the label is the
module's whole effect.

The answer is read off the body's shape alone. The request path and the
HTTP method are not consulted, and are not passed in: the async PFB
export posts the same participant-bearing query body to
``/hpds/auth/v3/query`` and to its ``/status`` and ``/result``
siblings, so no path tells the calls that carry participant work apart
from the ones that do not.

No request body and no response body is ever serialized into a dev-mode
event, whatever this module answers. An event carries a path, a method,
a status, byte counts and a duration, so the label marks which calls
carried participant-scoped work rather than standing in for a body that
would otherwise have been written down. Nothing here scrubs a secret out
of anything, and nothing here is on the path a token takes.

``_SENSITIVE_RESULT_TYPES`` names the result types whose request body
asks for per-patient rows: the two dataframe types, the PFB export, and
the VCF excerpt, whose response carries one genotype column per patient.

The aggregate variant result types (``AGGREGATE_VCF_EXCERPT``,
``VARIANT_COUNT_FOR_QUERY`` and ``VARIANT_LIST_FOR_QUERY``) are left off
the list on purpose. Their output is variant-level, with no patient row
in it, so the request body is as ordinary as a count.
"""

from __future__ import annotations

from typing import Any

_SENSITIVE_RESULT_TYPES = {
    "DATAFRAME",
    "DATAFRAME_TIMESERIES",
    "DATAFRAME_PFB",
    "VCF_EXCERPT",
}


def body_is_sensitive(body: dict[str, Any] | list[Any] | None) -> bool:
    """Whether the event for this request should be labelled participant-bearing.

    Args:
        body: The JSON request body, or ``None``.

    Returns:
        ``True`` when the body asks the backend for per-patient rows.
    """
    if body is None:
        return False
    return _body_is_participant_like(body)


def _body_is_participant_like(body: Any) -> bool:
    """Read the body's ``expectedResultType`` and look it up in the set.

    A body that is not an object, or that carries no ``query`` object,
    asks for no per-patient rows and answers ``False``.
    """
    query = body.get("query") if isinstance(body, dict) else None
    if not isinstance(query, dict):
        return False
    result_type = query.get("expectedResultType")
    return result_type in _SENSITIVE_RESULT_TYPES
