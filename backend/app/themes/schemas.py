from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


_SLUG_DISALLOWED_RE = re.compile(r"[^a-z0-9]+")


def slugify_theme_name(value: str) -> str:
    slug = _SLUG_DISALLOWED_RE.sub("-", value.strip().lower()).strip("-")
    if not slug:
        raise ValueError("theme name cannot be converted into a valid slug")
    return slug


class ThemeQextInput(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=300)
    version: str | None = Field(default=None, max_length=40)
    author: str | None = Field(default=None, max_length=120)
    homepage: str | None = Field(default=None, max_length=300)
    icon: str | None = Field(default=None, max_length=200)
    preview: str | None = Field(default=None, max_length=200)
    keywords: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("name", "description", "version", "author", "homepage", "icon", "preview")
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.strip().split())
        return normalized or None

    @field_validator("keywords")
    def normalize_keywords(cls, values: list[str]) -> list[str]:
        out: list[str] = []
        for value in values:
            normalized = " ".join(str(value).strip().split())
            if normalized:
                out.append(normalized)
        return out


class ThemeBuildRequest(BaseModel):
    theme_name: str = Field(min_length=3, max_length=64)
    file_basename: str | None = Field(default=None, min_length=1, max_length=80)
    qext: ThemeQextInput = Field(default_factory=ThemeQextInput)
    theme_json: dict[str, Any] = Field(default_factory=lambda: {"_inherit": True})

    @field_validator("theme_name")
    def normalize_theme_name(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("theme_name cannot be empty")
        return normalized

    @field_validator("file_basename")
    def normalize_file_basename(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return slugify_theme_name(value)

    @field_validator("theme_json")
    def validate_theme_json_root_object(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("theme_json must be a JSON object")
        return value


class ThemeUploadStubRequest(BaseModel):
    target: str | None = Field(default=None, max_length=120)

    @field_validator("target")
    def normalize_target(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.strip().split())
        return normalized or None


class ThemeUploadStubResponse(BaseModel):
    status: Literal["not_implemented"]
    detail: str
