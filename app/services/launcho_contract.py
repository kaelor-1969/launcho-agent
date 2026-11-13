"""Local adapter contract aligned with the existing conversation core, not an upstream specification."""
from typing import Literal

from pydantic import Field

from app.models.schemas import DomainChoice, Preferences


class DraftRequest(Preferences):
    businessName: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=100)
    planMonths: Literal[3, 6, 12]
    template: str = Field(min_length=1, max_length=100)
    domain: DomainChoice


def normalize_draft(payload: dict) -> dict:
    """Canonical JSON payload: reject unknown/null required fields; omit null domain alternatives."""
    # Literal accepts numerically equal floats/bools; transport must match core's strict integer.
    if type(payload.get('planMonths')) is not int:
        raise ValueError('planMonths must be an integer.')
    return DraftRequest.model_validate(payload).model_dump(mode='json', exclude_none=True)
