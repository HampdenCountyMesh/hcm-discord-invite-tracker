from __future__ import annotations

import csv
import io
import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterable

from .catalog import SourceCatalog
from .matching import InviteSnapshot


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._migrate()

    def _migrate(self) -> None:
        with self._lock, self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sources (
                    slug TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    route TEXT,
                    description TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    config_managed INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS invites (
                    code TEXT PRIMARY KEY,
                    guild_id TEXT NOT NULL,
                    source_slug TEXT REFERENCES sources(slug),
                    source_type TEXT NOT NULL,
                    channel_id TEXT,
                    channel_name TEXT,
                    inviter_id TEXT,
                    inviter_name TEXT,
                    source_created_by_id TEXT,
                    source_created_by_name TEXT,
                    uses INTEGER NOT NULL DEFAULT 0,
                    max_uses INTEGER NOT NULL DEFAULT 0,
                    max_age INTEGER NOT NULL DEFAULT 0,
                    temporary INTEGER NOT NULL DEFAULT 0,
                    discord_created_at TEXT,
                    expires_at TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_invites_source ON invites(source_slug);
                CREATE INDEX IF NOT EXISTS idx_invites_active ON invites(active);

                CREATE TABLE IF NOT EXISTS joins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    member_id TEXT,
                    member_name TEXT,
                    joined_at TEXT,
                    account_created_at TEXT,
                    invite_code TEXT,
                    source_slug TEXT,
                    source_type TEXT,
                    inviter_id TEXT,
                    inviter_name TEXT,
                    source_created_by_id TEXT,
                    source_created_by_name TEXT,
                    confidence TEXT NOT NULL,
                    match_reason TEXT NOT NULL,
                    raw_delta_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    identity_purged_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_joins_source ON joins(source_slug);
                CREATE INDEX IF NOT EXISTS idx_joins_recorded ON joins(recorded_at);
                CREATE INDEX IF NOT EXISTS idx_joins_member ON joins(member_id);
                """
            )

    def seed_sources(self, catalog: SourceCatalog) -> None:
        now = utc_now()
        with self._lock, self.conn:
            configured = {item.slug for item in catalog.sources}
            for item in catalog.sources:
                self.conn.execute(
                    """
                    INSERT INTO sources (
                        slug, display_name, route, description, active,
                        config_managed, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 1, 1, ?, ?)
                    ON CONFLICT(slug) DO UPDATE SET
                        display_name=excluded.display_name,
                        route=excluded.route,
                        description=excluded.description,
                        active=1,
                        config_managed=1,
                        updated_at=excluded.updated_at
                    """,
                    (
                        item.slug,
                        item.display_name,
                        item.route,
                        item.description,
                        now,
                        now,
                    ),
                )
            if configured:
                placeholders = ",".join("?" for _ in configured)
                self.conn.execute(
                    f"""
                    UPDATE sources
                    SET active=0, updated_at=?
                    WHERE config_managed=1 AND slug NOT IN ({placeholders})
                    """,
                    (now, *sorted(configured)),
                )

    def ensure_special_source(self, slug: str, display_name: str) -> None:
        now = utc_now()
        with self._lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO sources (
                    slug, display_name, active, config_managed, created_at, updated_at
                ) VALUES (?, ?, 1, 0, ?, ?)
                ON CONFLICT(slug) DO UPDATE SET
                    display_name=excluded.display_name,
                    active=1,
                    updated_at=excluded.updated_at
                """,
                (slug, display_name, now, now),
            )

    def mark_all_invites_inactive(self, guild_id: int) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                "UPDATE invites SET active=0, updated_at=? WHERE guild_id=?",
                (utc_now(), str(guild_id)),
            )

    def upsert_invite(
        self,
        guild_id: int,
        snapshot: InviteSnapshot,
        *,
        source_slug: str | None = None,
        source_type: str | None = None,
        source_created_by_id: str | None = None,
        source_created_by_name: str | None = None,
    ) -> None:
        now = utc_now()
        existing = self.get_invite(snapshot.code)
        resolved_source = source_slug if source_slug is not None else (
            existing["source_slug"] if existing else None
        )
        resolved_type = source_type if source_type is not None else (
            existing["source_type"] if existing else "unmapped"
        )
        resolved_creator_id = (
            source_created_by_id
            if source_created_by_id is not None
            else (existing["source_created_by_id"] if existing else None)
        )
        resolved_creator_name = (
            source_created_by_name
            if source_created_by_name is not None
            else (existing["source_created_by_name"] if existing else None)
        )
        with self._lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO invites (
                    code, guild_id, source_slug, source_type, channel_id, channel_name,
                    inviter_id, inviter_name, source_created_by_id,
                    source_created_by_name, uses, max_uses, max_age, temporary,
                    discord_created_at, expires_at, active, first_seen_at,
                    last_seen_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    guild_id=excluded.guild_id,
                    source_slug=excluded.source_slug,
                    source_type=excluded.source_type,
                    channel_id=excluded.channel_id,
                    channel_name=excluded.channel_name,
                    inviter_id=excluded.inviter_id,
                    inviter_name=excluded.inviter_name,
                    source_created_by_id=excluded.source_created_by_id,
                    source_created_by_name=excluded.source_created_by_name,
                    uses=excluded.uses,
                    max_uses=excluded.max_uses,
                    max_age=excluded.max_age,
                    temporary=excluded.temporary,
                    discord_created_at=excluded.discord_created_at,
                    expires_at=excluded.expires_at,
                    active=1,
                    last_seen_at=excluded.last_seen_at,
                    updated_at=excluded.updated_at
                """,
                (
                    snapshot.code,
                    str(guild_id),
                    resolved_source,
                    resolved_type,
                    snapshot.channel_id,
                    snapshot.channel_name,
                    snapshot.inviter_id,
                    snapshot.inviter_name,
                    resolved_creator_id,
                    resolved_creator_name,
                    snapshot.uses,
                    snapshot.max_uses,
                    snapshot.max_age,
                    int(snapshot.temporary),
                    snapshot.created_at,
                    snapshot.expires_at,
                    now,
                    now,
                    now,
                ),
            )

    def map_invite(
        self,
        code: str,
        source_slug: str,
        source_type: str,
        actor_id: str | None,
        actor_name: str | None,
    ) -> None:
        with self._lock, self.conn:
            cursor = self.conn.execute(
                """
                UPDATE invites
                SET source_slug=?, source_type=?, source_created_by_id=?,
                    source_created_by_name=?, updated_at=?
                WHERE code=?
                """,
                (
                    source_slug,
                    source_type,
                    actor_id,
                    actor_name,
                    utc_now(),
                    code,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Invite {code} is not present in the database")

    def get_invite(self, code: str) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(
                "SELECT * FROM invites WHERE code=?", (code,)
            ).fetchone()

    def invite_for_source(self, source_slug: str) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(
                """
                SELECT * FROM invites
                WHERE source_slug=? AND active=1
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (source_slug,),
            ).fetchone()

    def list_sources_with_invites(self) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(
                """
                SELECT s.slug, s.display_name, s.route, s.description, s.active,
                       i.code, i.source_type, i.uses, i.channel_name,
                       i.inviter_name, i.source_created_by_name, i.last_seen_at
                FROM sources s
                LEFT JOIN invites i ON i.code = (
                    SELECT i2.code FROM invites i2
                    WHERE i2.source_slug=s.slug AND i2.active=1
                    ORDER BY i2.updated_at DESC LIMIT 1
                )
                ORDER BY s.config_managed DESC, s.slug
                """
            ).fetchall()

    def list_invites(self, *, active_only: bool = False) -> list[sqlite3.Row]:
        sql = "SELECT * FROM invites"
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY active DESC, updated_at DESC"
        with self._lock:
            return self.conn.execute(sql).fetchall()

    def record_join(
        self,
        *,
        member_id: str,
        member_name: str,
        joined_at: str | None,
        account_created_at: str | None,
        invite_code: str | None,
        confidence: str,
        match_reason: str,
        deltas: dict[str, int],
    ) -> None:
        invite = self.get_invite(invite_code) if invite_code else None
        with self._lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO joins (
                    member_id, member_name, joined_at, account_created_at,
                    invite_code, source_slug, source_type, inviter_id,
                    inviter_name, source_created_by_id, source_created_by_name,
                    confidence, match_reason, raw_delta_json, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    member_id,
                    member_name,
                    joined_at,
                    account_created_at,
                    invite_code,
                    invite["source_slug"] if invite else None,
                    invite["source_type"] if invite else None,
                    invite["inviter_id"] if invite else None,
                    invite["inviter_name"] if invite else None,
                    invite["source_created_by_id"] if invite else None,
                    invite["source_created_by_name"] if invite else None,
                    confidence,
                    match_reason,
                    json.dumps(deltas, sort_keys=True),
                    utc_now(),
                ),
            )

    def source_summary(self) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(
                """
                SELECT COALESCE(source_slug, 'unknown') AS source_slug,
                       COUNT(*) AS join_count,
                       SUM(CASE WHEN confidence='normal' THEN 1 ELSE 0 END) AS normal_count,
                       MAX(recorded_at) AS latest_join
                FROM joins
                GROUP BY COALESCE(source_slug, 'unknown')
                ORDER BY join_count DESC, source_slug
                """
            ).fetchall()

    def recent_joins(self, limit: int = 25) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(
                """
                SELECT * FROM joins ORDER BY recorded_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def total_joins(self) -> int:
        with self._lock:
            row = self.conn.execute("SELECT COUNT(*) AS count FROM joins").fetchone()
            return int(row["count"])

    def purge_identities(self, retention_days: int) -> int:
        if retention_days <= 0:
            return 0
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
        now = utc_now()
        with self._lock, self.conn:
            cursor = self.conn.execute(
                """
                UPDATE joins
                SET member_id=NULL, member_name=NULL, account_created_at=NULL,
                    identity_purged_at=?
                WHERE recorded_at < ? AND identity_purged_at IS NULL
                """,
                (now, cutoff),
            )
            return cursor.rowcount

    def backup(self, directory: Path, keep: int) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        destination = directory / f"invite-tracker-{stamp}.sqlite3"
        with self._lock:
            backup_conn = sqlite3.connect(destination)
            try:
                self.conn.backup(backup_conn)
            finally:
                backup_conn.close()
        backups = sorted(directory.glob("invite-tracker-*.sqlite3"), reverse=True)
        for old in backups[max(1, keep) :]:
            old.unlink(missing_ok=True)
        return destination

    def csv_export(self, rows: Iterable[sqlite3.Row]) -> bytes:
        row_list = list(rows)
        if not row_list:
            return b""
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=row_list[0].keys())
        writer.writeheader()
        for row in row_list:
            writer.writerow(dict(row))
        return stream.getvalue().encode("utf-8")

    def close(self) -> None:
        with self._lock:
            self.conn.close()
