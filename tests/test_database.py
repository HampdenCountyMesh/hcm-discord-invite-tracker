from pathlib import Path

from hcm_invite_tracker.catalog import SourceCatalog
from hcm_invite_tracker.database import Database
from hcm_invite_tracker.matching import InviteSnapshot
from hcm_invite_tracker.website import website_mapping


def test_mapping_and_join_record(tmp_path: Path):
    catalog_path = Path(__file__).parents[1] / "config" / "hcm-sources.yml"
    catalog = SourceCatalog.load(catalog_path)
    db = Database(tmp_path / "test.sqlite3")
    try:
        db.seed_sources(catalog)
        db.upsert_invite(
            123,
            InviteSnapshot(code="abc", uses=0),
            source_slug="site-nav",
            source_type="managed",
            source_created_by_id="1",
            source_created_by_name="admin",
        )
        db.record_join(
            member_id="2",
            member_name="member",
            joined_at=None,
            account_created_at=None,
            invite_code="abc",
            confidence="normal",
            match_reason="test",
            deltas={"abc": 1},
        )
        assert db.total_joins() == 1
        assert website_mapping(db)["sources"]["site-nav"].endswith("/abc")
    finally:
        db.close()


def test_special_source_is_not_exported_to_website(tmp_path: Path):
    catalog_path = Path(__file__).parents[1] / "config" / "hcm-sources.yml"
    catalog = SourceCatalog.load(catalog_path)
    db = Database(tmp_path / "test-special.sqlite3")
    try:
        db.seed_sources(catalog)
        db.ensure_special_source("member-invite", "Member-created invite")
        db.upsert_invite(
            123,
            InviteSnapshot(code="membercode", uses=1),
            source_slug="member-invite",
            source_type="user-created",
        )
        assert "member-invite" not in website_mapping(db)["sources"]
    finally:
        db.close()


def test_backup_is_created(tmp_path: Path):
    db = Database(tmp_path / "source.sqlite3")
    try:
        backup = db.backup(tmp_path / "backups", keep=2)
        assert backup.exists()
        assert backup.stat().st_size > 0
    finally:
        db.close()
