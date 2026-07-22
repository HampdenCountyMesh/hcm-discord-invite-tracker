from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml

from .database import Database


def website_mapping(db: Database) -> dict[str, object]:
    sources: dict[str, str] = {}
    for row in db.list_sources_with_invites():
        code = row["code"]
        # Only configured website routes belong in the Jekyll mapping.
        if code and row["route"]:
            sources[row["slug"]] = f"https://discord.gg/{code}"
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "generated_by": "hcm-discord-invite-tracker",
        "sources": sources,
    }


def render_website_mapping(db: Database) -> str:
    return yaml.safe_dump(website_mapping(db), sort_keys=False, allow_unicode=True)


def write_website_mapping(db: Database, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(render_website_mapping(db), encoding="utf-8")
    temp.replace(path)
    return path
