"""CountryProfile loader: countries/<CODE>.yaml → pydantic. The only place a country differs."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

log = logging.getLogger(__name__)


class Freshness(BaseModel):
    full_score_days: int = Field(ge=0)
    zero_score_days: int = Field(ge=1)

    @model_validator(mode="after")
    def _order(self) -> Freshness:
        if self.zero_score_days <= self.full_score_days:
            raise ValueError("zero_score_days must be greater than full_score_days")
        return self


class CountryProfile(BaseModel):
    code: str = Field(min_length=2, max_length=3)
    name: str
    languages: list[str]
    currency: str
    date_format: str
    source_hierarchy: dict[str, int]
    freshness: Freshness
    require_owner: bool
    escalation_threshold: int = Field(ge=0, le=100)
    expert_tags: list[str]
    context_notes: str = ""

    @field_validator("code")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @field_validator("source_hierarchy")
    @classmethod
    def _hierarchy(cls, v: dict[str, int]) -> dict[str, int]:
        if not v:
            raise ValueError("source_hierarchy must not be empty")
        if "expert_answer" not in v:
            raise ValueError("source_hierarchy must contain 'expert_answer' (self-healing loop writes it)")
        if any(int(x) <= 0 for x in v.values()):
            raise ValueError("source_hierarchy values must be positive")
        return v

    @property
    def max_authority(self) -> int:
        return max(self.source_hierarchy.values())

    def public(self) -> dict:
        return {"code": self.code, "name": self.name, "languages": self.languages}


class CountryRegistry:
    def __init__(self, profiles: dict[str, CountryProfile]):
        self._profiles = profiles

    def get(self, code: str) -> CountryProfile:
        try:
            return self._profiles[code.upper()]
        except KeyError as exc:
            raise KeyError(f"unknown country '{code}'") from exc

    def has(self, code: str) -> bool:
        return code.upper() in self._profiles

    @property
    def codes(self) -> list[str]:
        return sorted(self._profiles)

    def all(self) -> list[CountryProfile]:
        return [self._profiles[c] for c in self.codes]

    def source_types_for(self, code: str) -> list[str]:
        return list(self.get(code).source_hierarchy)


def load_registry(countries_dir: Path) -> CountryRegistry:
    """Load every countries/*.yaml except files starting with '_'. Fails loudly on a bad file."""
    profiles: dict[str, CountryProfile] = {}
    files = sorted(p for p in countries_dir.glob("*.yaml") if not p.name.startswith("_"))
    if not files:
        raise RuntimeError(f"no country profiles found in {countries_dir}")
    for path in files:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        try:
            profile = CountryProfile.model_validate(raw)
        except Exception as exc:  # noqa: BLE001 - we want the file name in the error
            raise RuntimeError(f"invalid country profile {path.name}: {exc}") from exc
        if profile.code != path.stem.upper():
            raise RuntimeError(f"{path.name}: code '{profile.code}' does not match filename")
        profiles[profile.code] = profile
        log.info("loaded country profile %s (%s)", profile.code, profile.name)
    return CountryRegistry(profiles)
