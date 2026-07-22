from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    slug: str
    display_name: str
    route: str | None = None
    description: str | None = None
    preferred_invite_code: str | None = None
    provision: bool = True


@dataclass(frozen=True, slots=True)
class SourceCatalog:
    project_name: str
    site_base_url: str | None
    sources: tuple[SourceDefinition, ...]

    @classmethod
    def load(cls, path: str | Path) -> "SourceCatalog":
        source_path = Path(path)
        with source_path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}

        project = raw.get("project") or {}
        definitions: list[SourceDefinition] = []
        seen: set[str] = set()

        for item in raw.get("sources") or []:
            if not isinstance(item, dict):
                raise ValueError("Every source entry must be a mapping")
            slug = str(item.get("slug", "")).strip()
            validate_slug(slug)
            if slug in seen:
                raise ValueError(f"Duplicate source slug: {slug}")
            seen.add(slug)
            definitions.append(
                SourceDefinition(
                    slug=slug,
                    display_name=str(item.get("display_name") or slug),
                    route=_optional_text(item.get("route")),
                    description=_optional_text(item.get("description")),
                    preferred_invite_code=_optional_text(item.get("preferred_invite_code")),
                    provision=bool(item.get("provision", True)),
                )
            )

        if not definitions:
            raise ValueError("The source catalog must define at least one source")

        return cls(
            project_name=str(project.get("name") or "Discord Invite Tracker"),
            site_base_url=_optional_text(project.get("site_base_url")),
            sources=tuple(definitions),
        )

    def by_slug(self, slug: str) -> SourceDefinition | None:
        return next((item for item in self.sources if item.slug == slug), None)

    def as_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "slug": item.slug,
                "display_name": item.display_name,
                "route": item.route,
                "description": item.description,
            }
            for item in self.sources
        ]


def validate_slug(slug: str) -> None:
    if not _SLUG_RE.fullmatch(slug):
        raise ValueError(
            "Source slugs must use lowercase letters, numbers, and single hyphens"
        )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
