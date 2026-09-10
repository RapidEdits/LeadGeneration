"""Bounded inputs for public business prospecting."""
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


class ProductProfile(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    overview: str = Field(min_length=20, max_length=6000)
    website: HttpUrl
    target_customer: str = Field(min_length=3, max_length=300)
    locations: list[str] = Field(min_length=1, max_length=5)
    country_code: str = Field(default="ALL", pattern=r"^(ALL|[A-Z]{2})$")
    radius_km: float | None = Field(default=None, gt=0, le=1000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    max_leads: int = Field(default=25, ge=1, le=100)

    @field_validator("locations")
    @classmethod
    def clean_locations(cls, values):
        values = list(dict.fromkeys(v.strip() for v in values if v.strip()))
        if not values or any(len(v) > 120 for v in values):
            raise ValueError("Provide 1–5 locations, each at most 120 characters")
        return values

    @model_validator(mode="after")
    def radius_center(self):
        if self.radius_km is not None and (self.latitude is None or self.longitude is None):
            raise ValueError("Radius targeting requires center latitude and longitude")
        return self


class DiscoveryRequest(BaseModel):
    mode: Literal["search", "websites"] = "search"
    websites: list[HttpUrl] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def supplied_sites(self):
        if self.mode == "websites" and not self.websites:
            raise ValueError("Provide at least one business website")
        return self


class ImportProspects(BaseModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=100)
    campaign_id: str | None = Field(default=None, max_length=36)


class SearchCredentials(BaseModel):
    api_key: str = Field(min_length=1, max_length=512)

    @field_validator("api_key")
    @classmethod
    def nonempty_key(cls, value):
        if not value.strip():
            raise ValueError("Search API key must not be blank")
        return value.strip()
