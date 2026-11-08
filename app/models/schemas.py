from typing import Literal
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.core.privacy import reject_sensitive


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class DomainChoice(StrictModel):
    label: str | None = None
    tld: str | None = None
    ownDomain: str | None = None

    @field_validator('label','tld','ownDomain')
    @classmethod
    def domain_has_no_contact(cls,value):
        return reject_sensitive(value) if value is not None else value

    @model_validator(mode='after')
    def validate_domain(self):
        if self.ownDomain:
            if self.label or self.tld or not re.fullmatch(r'(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,24}', self.ownDomain):
                raise ValueError('دامنه معتبر نیست.')
        elif not (self.label and self.tld and re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', self.label) and re.fullmatch(r'[a-z]{2,24}', self.tld)):
            raise ValueError('نام و پسوند دامنه لازم است.')
        return self


class Preferences(StrictModel):
    kind: Literal['shop', 'website'] = 'shop'
    businessName: str | None = Field(default=None, min_length=1, max_length=80)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    planMonths: int | None = Field(default=None, strict=True, ge=1, le=120)
    template: str | None = Field(default=None, min_length=1, max_length=100)
    domain: DomainChoice | None = None

    @field_validator('businessName', 'category', 'template')
    @classmethod
    def no_sensitive_fields(cls, value):
        return reject_sensitive(value) if value is not None else value


class PreferenceUpdate(StrictModel):
    kind: Literal['shop', 'website'] | None = None
    businessName: str | None = Field(default=None, min_length=1, max_length=80)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    planMonths: int | None = Field(default=None, strict=True, ge=1, le=120)
    template: str | None = Field(default=None, min_length=1, max_length=100)
    domain: DomainChoice | None = None


class ChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=5000)
    sessionId: str | None = Field(default=None, min_length=16, max_length=100)

    @field_validator('message')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('پیام خالی است.')
        return value.strip()


class ChatResponse(BaseModel):
    reply: str
    sessionId: str | None = None
    revision: int | None = None
    preferences: dict | None = None
    nextAction: str | None = None


class EditRequest(StrictModel):
    revision: int = Field(ge=0, strict=True)
    preferences: PreferenceUpdate


class ReviewRequest(StrictModel):
    revision: int = Field(ge=0, strict=True)


class ConfirmRequest(ReviewRequest):
    reviewId: str = Field(min_length=16, max_length=100)
    confirmationToken: str = Field(min_length=24, max_length=200)
    confirmed: bool = Field(strict=True)


class ResumeRequest(StrictModel):
    signupRef: str = Field(pattern=r'^sd_[A-Za-z0-9_-]{4,128}$')
