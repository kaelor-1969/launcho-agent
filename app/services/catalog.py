"""Versioned local catalog validation. Approval metadata is not an official API contract."""
from datetime import date
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ApprovalStatus = Literal['test_only', 'pending', 'approved', 'inactive']
ServiceKind = Literal['shop', 'website']


class CatalogModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class CatalogSource(CatalogModel):
    type: Literal['internal_fixture', 'official_api', 'official_page', 'unverified']
    reference: str = Field(min_length=1)


class CatalogOption(CatalogModel):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=120)
    kind: ServiceKind
    available: bool = Field(strict=True)
    approvalStatus: ApprovalStatus
    source: CatalogSource
    reviewedAt: date
    approvalEvidence: str | None = Field(default=None, min_length=1)

    @model_validator(mode='after')
    def approval_consistency(self):
        if self.approvalStatus in {'pending', 'inactive'} and self.available:
            raise ValueError('Pending/inactive options cannot be available.')
        if self.approvalStatus == 'approved' and (
                self.source.type != 'official_api' or not self.approvalEvidence):
            raise ValueError('Approved registration options require official API provenance and approval evidence.')
        if self.approvalStatus == 'test_only' and self.source.type != 'internal_fixture':
            raise ValueError('Test options require an internal fixture source.')
        return self


class BusinessCategory(CatalogOption):
    label: str = Field(min_length=1, max_length=120)


class Template(CatalogOption):
    compatibleCategoryIds: list[str] | None


class SignupCatalog(CatalogModel):
    catalogVersion: Literal['1.0.0']
    kind: ServiceKind
    availability: Literal['unavailable', 'test_only', 'available']
    notice: str = Field(min_length=1)
    approvalStatus: ApprovalStatus
    source: CatalogSource
    reviewedAt: date
    steps: list = Field(default_factory=list)
    businessCategories: list[BusinessCategory]
    templateCategories: list = Field(default_factory=list)
    templates: list[Template]

    @model_validator(mode='after')
    def relationships(self):
        if self.approvalStatus == 'approved' and self.source.type != 'official_api':
            raise ValueError('Approved catalogs require official API provenance.')
        if self.approvalStatus == 'test_only' and self.source.type != 'internal_fixture':
            raise ValueError('Test catalogs require an internal fixture source.')
        if self.availability == 'test_only' and self.approvalStatus != 'test_only':
            raise ValueError('Test availability requires test-only approval status.')
        if self.availability == 'available' and self.approvalStatus != 'approved':
            raise ValueError('Available production catalogs require approval.')
        for entries in (self.businessCategories, self.templates):
            ids = [entry.id for entry in entries]
            if len(set(ids)) != len(ids) or any(entry.kind != self.kind for entry in entries):
                raise ValueError('Duplicate IDs or wrong service kind in catalog.')
        ids = {entry.id for entry in self.businessCategories}
        for template in self.templates:
            compatible = template.compatibleCategoryIds
            if compatible is not None and (len(set(compatible)) != len(compatible) or not set(compatible) <= ids):
                raise ValueError('Template refers to unknown/duplicate category IDs.')
            if template.available and compatible == []:
                raise ValueError('Available template cannot have an empty compatibility list.')
        return self


def selectable_catalog(raw, kind, *, allow_test=False):
    catalog = SignupCatalog.model_validate(raw)
    if catalog.kind != kind:
        raise ValueError('Catalog service kind mismatch.')
    data = catalog.model_dump(mode='json')
    allowed = {'approved', 'test_only'} if allow_test else {'approved'}
    if catalog.availability == 'unavailable' or catalog.approvalStatus not in allowed:
        data['businessCategories'], data['templates'] = [], []
        data['availability'] = 'unavailable'
        return data
    data['businessCategories'] = [entry for entry in data['businessCategories']
                                  if entry['available'] and entry['approvalStatus'] in allowed]
    category_ids = {entry['id'] for entry in data['businessCategories']}
    selected = []
    for template in data['templates']:
        if not template['available'] or template['approvalStatus'] not in allowed:
            continue
        if template['compatibleCategoryIds'] is not None:
            template['compatibleCategoryIds'] = [key for key in template['compatibleCategoryIds'] if key in category_ids]
            if not template['compatibleCategoryIds']:
                continue
        selected.append(template)
    data['templates'] = selected
    if not data['businessCategories'] or not data['templates']:
        data['availability'] = 'unavailable'
        data['businessCategories'], data['templates'] = [], []
    return data


def documented_catalog(kind):
    if kind not in {'shop', 'website'}:
        raise ValueError('Invalid service kind.')
    path = Path(__file__).resolve().parents[2] / 'content' / 'launcho-mock.json'
    return selectable_catalog(json.loads(path.read_text(encoding='utf-8'))['signupOptions'][kind], kind)
