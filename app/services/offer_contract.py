"""Internal offer coordination contract, not the official Launcho API schema."""
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.privacy import reject_sensitive

OfferStage = Literal['guidance', 'collecting_preferences', 'review_ready',
                     'awaiting_confirmation', 'draft_created']
OFFER_STAGES = frozenset(OfferStage.__args__)


class OfferState(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    shownOfferIds: list[str] = Field(default_factory=list)
    rejectedOfferIds: list[str] = Field(default_factory=list)
    anyFinancialOfferShown: bool = False
    financialOffersDeclined: bool = False

    @field_validator('shownOfferIds', 'rejectedOfferIds')
    @classmethod
    def valid_ids(cls, values):
        import re
        if len(values) > 1000 or len(values) != len(set(values)) or any(
                not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value) for value in values):
            raise ValueError('Invalid persisted offer IDs.')
        return values


class OfferSource(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    type: Literal['internal_fixture', 'official_api']
    reference: str = Field(min_length=1, max_length=500)
    approvalEvidence: str | None = Field(default=None, min_length=1, max_length=500)


class FinancialOffer(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    offerId: str = Field(pattern=r'^[A-Za-z0-9_-]{1,100}$')
    type: Literal['payment_option', 'discount']
    kind: Literal['shop', 'website']
    displayText: str = Field(min_length=1, max_length=160)
    expiresAt: datetime
    source: OfferSource
    simulation: bool = Field(strict=True)
    eligibleStages: list[OfferStage] = Field(min_length=1)
    planMonths: list[Literal[3, 6, 12]] = Field(min_length=1)

    @field_validator('displayText')
    @classmethod
    def plain_safe_text(cls, value):
        # Link targets and markup come from application-owned UI, never offer prose.
        if any(token in value.lower() for token in ('http:', 'https:', 'www.', '//', 'javascript:',
                                                   'data:', '<', '>', '[', ']', '`', '\n', '\r')):
            raise ValueError('Offer text must be plain text without links.')
        return reject_sensitive(value)

    @field_validator('expiresAt', mode='before')
    @classmethod
    def explicit_timestamp(cls, value):
        if not isinstance(value, (str, datetime)):
            raise ValueError('Explicit timestamp required.')
        return value

    @model_validator(mode='after')
    def provenance_and_time(self):
        if self.expiresAt.tzinfo is None or self.expiresAt.utcoffset() is None:
            raise ValueError('Timezone required.')
        if len(set(self.eligibleStages)) != len(self.eligibleStages) or len(set(self.planMonths)) != len(self.planMonths):
            raise ValueError('Duplicate eligibility values.')
        if self.simulation:
            if self.source.type != 'internal_fixture':
                raise ValueError('Fixture provenance required.')
        else:
            url = urlsplit(self.source.reference)
            if (self.source.type != 'official_api' or not self.source.approvalEvidence
                    or url.scheme != 'https' or url.hostname != 'launcho.ir'
                    or url.username or url.password or url.port not in (None, 443)
                    or url.query or url.fragment):
                raise ValueError('Approved official provenance required.')
        return self


def validated_offers(data, *, kind, stage, plan_months=None, allow_simulation=False,
                     state=None, now=None):
    """Reject malformed envelopes; skip ineligible, expired or previously handled offers."""
    if not isinstance(data, dict) or not isinstance(data.get('offers'), list):
        raise ValueError('Invalid offer envelope.')
    state = OfferState.model_validate(state or {})
    now = now or datetime.now(timezone.utc)
    result, seen = [], set()
    for raw in data['offers']:
        offer = FinancialOffer.model_validate(raw)
        if offer.offerId in seen:
            raise ValueError('Duplicate offer ID.')
        seen.add(offer.offerId)
        if (state.anyFinancialOfferShown or state.financialOffersDeclined or state.shownOfferIds
                or offer.offerId in state.rejectedOfferIds
                or offer.kind != kind or stage not in offer.eligibleStages
                or offer.expiresAt <= now or (offer.simulation and not allow_simulation)
                or (plan_months is not None and plan_months not in offer.planMonths)):
            continue
        result.append(offer.model_dump(mode='json'))
    return {'offers': result}
