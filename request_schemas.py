"""Typed request-body schemas (cq-pydantic).

Every JSON endpoint already declares its fields with api_contract.json_object(
required=..., optional=...). This module turns that declaration into a strict
pydantic model: unknown fields are rejected (extra='forbid'), required fields
must be present, and fields with a known type must have exactly that type or be
null (no silent coercion: "true" is not a boolean, "3" is not an integer; null is
left to the service, which already answers it, e.g. 409 for a stale revision). Field types
come from FIELD_TYPES, one table for the whole API, because field names mean
the same thing everywhere. Names not listed are accepted as any JSON value and
are still validated by the service code.

Status code: DHASHU_VALIDATION_STATUS (default 400, unchanged for installed apps;
set 422 once a mobile build that treats 422 as a validation error is live —
the mobile client in this branch already does).

tools/gen_openapi_schemas.py builds the OpenAPI requestBody schemas from the
same models (model_for), so the document cannot drift from what is enforced.
"""
import os
from functools import lru_cache
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, ValidationError, create_model

Text = Annotated[StrictStr, Field(max_length=10_000)]
Id = Annotated[StrictStr, Field(min_length=1, max_length=256)]
Image = Annotated[StrictStr, Field(max_length=3_000_000)]   # data: URLs; services enforce the real image limits
Count = Annotated[StrictInt, Field(ge=-1_000_000, le=1_000_000)]
List = Annotated[list, Field(max_length=500)]

FIELD_TYPES = {
    # identifiers and short strings
    **{name: Id for name in (
        'request_id', 'session_id', 'proposal_id', 'candidate_id', 'memory_id', 'quote_id', 'question_key',
        'consent_version', 'action', 'step', 'stage', 'topic', 'pillar', 'product', 'reference', 'channel',
        'decision', 'choice', 'operation', 'template', 'preset', 'scope', 'meal_slot', 'response', 'type',
        'key', 'stance', 'strategy', 'category', 'document_sha256', 'gender', 'city')},
    # free text
    **{name: Text for name in (
        'text', 'note', 'answer_text', 'custom_question', 'reason', 'pass_reason', 'signed_name', 'contact_value',
        'employer', 'title', 'label', 'idea', 'name')},
    # images
    'image': Image, 'photo': Image,
    # strict booleans
    **{name: StrictBool for name in (
        'consent', 'share_health', 'disclosed_to_partner', 'together_photo', 'bill_photo', 'share_feedback',
        'declined', 'consent_completed', 'acknowledged', 'accept_recurring', 'include_undisclosed', 'enabled',
        'shared', 'compliant')},
    # integers
    **{name: Count for name in ('revision', 'index', 'advance_hours', 'max_per_person_minor', 'cycle')},
    # lists
    **{name: List for name in (
        'slots', 'acks', 'categories', 'neighbourhoods', 'green_flags', 'red_flags',
        'custom_activities', 'partner_any', 'add', 'remove', 'open_categories', 'question_keys', 'custom_pillars')},
    # 'activities' and 'pillars' are lists on some routes and objects on others: untyped here.
    # objects
    **{name: dict for name in ('fields', 'values', 'inputs', 'declared')},
}


class _Base(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


def _model_name(required, optional):
    return 'Body_' + '_'.join(sorted(required)) + ('__opt_' + '_'.join(sorted(optional)) if optional else '')


@lru_cache(maxsize=1024)
def model_for(required, optional):
    """required/optional: frozensets of field names. Cached per field set."""
    fields = {}
    for name in sorted(required | optional):
        kind = FIELD_TYPES.get(name, Any)
        # null is accepted for typed fields and left to the service: a stale client sending
        # revision/scope null must still get the service's 409 (refresh), not a schema 400.
        nullable = Any if kind is Any else kind | None
        fields[name] = (nullable, ...) if name in required else (nullable, None)
    return create_model(_model_name(required, optional)[:200], __base__=_Base, **fields)


def status():
    value = os.environ.get('DHASHU_VALIDATION_STATUS', '400')
    return 422 if value == '422' else 400


def describe(error: ValidationError, limit=5):
    """Short, safe message: field names and the problem, never the submitted values."""
    parts = []
    for item in error.errors()[:limit]:
        where = '.'.join(str(p) for p in item.get('loc', ())) or 'body'
        kind = item.get('type', '')
        problem = {'missing': 'is required', 'extra_forbidden': 'is not an accepted field'}.get(kind)
        if problem is None:
            problem = 'has the wrong type' if kind.endswith('_type') or kind.endswith('_parsing') else 'is not valid'
        parts.append(f'{where} {problem}')
    return '; '.join(parts)


def validate(body, required, optional):
    """Raises ValidationError; returns the original body (services keep their own parsing)."""
    model_for(frozenset(required), frozenset(optional)).model_validate(body)
    return body
