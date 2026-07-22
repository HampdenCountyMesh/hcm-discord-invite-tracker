from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Settings:
    discord_token: str
    guild_id: int
    log_channel_id: int | None
    default_invite_channel_id: int | None
    admin_role_ids: frozenset[int]
    database_path: Path
    source_config_path: Path
    website_export_path: Path
    backup_dir: Path
    backup_keep: int
    identity_retention_days: int
    timezone: str
    dashboard_enabled: bool
    dashboard_host: str
    dashboard_port: int
    dashboard_username: str | None
    dashboard_password: str | None
    invite_refresh_seconds: int
    log_level: str


def load_settings() -> Settings:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise ConfigError("DISCORD_TOKEN is required")

    guild_id = _required_int("GUILD_ID")
    timezone = os.getenv("TIMEZONE", "America/New_York").strip()
    try:
        ZoneInfo(timezone)
    except Exception as exc:  # pragma: no cover - platform zoneinfo failure
        raise ConfigError(f"Invalid TIMEZONE: {timezone}") from exc

    username = _optional_text("DASHBOARD_USERNAME")
    password = _optional_text("DASHBOARD_PASSWORD")
    if bool(username) != bool(password):
        raise ConfigError(
            "DASHBOARD_USERNAME and DASHBOARD_PASSWORD must either both be set or both be empty"
        )

    return Settings(
        discord_token=token,
        guild_id=guild_id,
        log_channel_id=_optional_int("LOG_CHANNEL_ID"),
        default_invite_channel_id=_optional_int("DEFAULT_INVITE_CHANNEL_ID"),
        admin_role_ids=frozenset(_csv_ints(os.getenv("ADMIN_ROLE_IDS", ""))),
        database_path=Path(os.getenv("DATABASE_PATH", "/data/invite-tracker.sqlite3")),
        source_config_path=Path(
            os.getenv("SOURCE_CONFIG_PATH", "/app/config/hcm-sources.yml")
        ),
        website_export_path=Path(
            os.getenv("WEBSITE_EXPORT_PATH", "/data/discord-invites.yml")
        ),
        backup_dir=Path(os.getenv("BACKUP_DIR", "/data/backups")),
        backup_keep=max(1, int(os.getenv("BACKUP_KEEP", "14"))),
        identity_retention_days=max(
            0, int(os.getenv("IDENTITY_RETENTION_DAYS", "90"))
        ),
        timezone=timezone,
        dashboard_enabled=_bool("DASHBOARD_ENABLED", True),
        dashboard_host=os.getenv("DASHBOARD_HOST", "0.0.0.0").strip(),
        dashboard_port=int(os.getenv("DASHBOARD_PORT", "8091")),
        dashboard_username=username,
        dashboard_password=password,
        invite_refresh_seconds=max(
            60, int(os.getenv("INVITE_REFRESH_SECONDS", "600"))
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper().strip(),
    )


def _required_int(name: str) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required")
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc


def _optional_int(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc


def _optional_text(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def _csv_ints(value: str) -> set[int]:
    result: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if item:
            try:
                result.add(int(item))
            except ValueError as exc:
                raise ConfigError("ADMIN_ROLE_IDS must be comma-separated integers") from exc
    return result


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be true or false")
