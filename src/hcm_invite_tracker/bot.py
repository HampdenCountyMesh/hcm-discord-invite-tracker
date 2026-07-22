from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import discord
from discord.ext import commands, tasks

from .catalog import SourceCatalog
from .config import Settings
from .database import Database
from .discord_helpers import snapshot_from_discord
from .matching import InviteMatch, InviteSnapshot, match_used_invite
from .website import write_website_mapping

LOG = logging.getLogger(__name__)


class InviteTrackerBot(commands.Bot):
    def __init__(self, settings: Settings, db: Database, catalog: SourceCatalog):
        intents = discord.Intents.none()
        intents.guilds = True
        intents.members = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.settings = settings
        self.db = db
        self.catalog = catalog
        self.invite_cache: dict[str, InviteSnapshot] = {}
        self.join_lock = asyncio.Lock()
        self._maintenance_started = False

    async def setup_hook(self) -> None:
        from .commands import ReportCommands, SourceCommands

        await self.add_cog(SourceCommands(self))
        await self.add_cog(ReportCommands(self))
        guild = discord.Object(id=self.settings.guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

    async def on_ready(self) -> None:
        guild = self.get_guild(self.settings.guild_id)
        if guild is None:
            LOG.error("Configured guild %s is not available to the bot", self.settings.guild_id)
            return
        await self.refresh_invites(guild, bootstrap=True)
        write_website_mapping(self.db, self.settings.website_export_path)
        if not self._maintenance_started:
            self.refresh_loop.change_interval(seconds=self.settings.invite_refresh_seconds)
            self.refresh_loop.start()
            self.maintenance_loop.start()
            self._maintenance_started = True
        LOG.info("Ready as %s in %s", self.user, guild.name)

    async def on_member_join(self, member: discord.Member) -> None:
        if member.guild.id != self.settings.guild_id:
            return
        async with self.join_lock:
            await self._process_join(member)

    async def _process_join(self, member: discord.Member) -> None:
        previous = dict(self.invite_cache)
        try:
            current = await self.fetch_invite_snapshots(member.guild)
        except discord.Forbidden:
            match = InviteMatch(
                None,
                "unknown",
                "bot lacks permission to fetch invite metadata",
                {},
            )
            current = previous
        except discord.HTTPException as exc:
            match = InviteMatch(None, "unknown", f"Discord invite fetch failed: {exc}", {})
            current = previous
        else:
            match = match_used_invite(previous, current)
            self._sync_invites_to_db(member.guild.id, current)
            self.invite_cache = current
            write_website_mapping(self.db, self.settings.website_export_path)

        self.db.record_join(
            member_id=str(member.id),
            member_name=str(member),
            joined_at=member.joined_at.isoformat() if member.joined_at else None,
            account_created_at=member.created_at.isoformat(),
            invite_code=match.code,
            confidence=match.confidence,
            match_reason=match.reason,
            deltas=match.deltas,
        )
        await self._send_join_log(member, match)

    async def _send_join_log(self, member: discord.Member, match: InviteMatch) -> None:
        invite = self.db.get_invite(match.code) if match.code else None
        lines = [
            f"New member joined: {member.mention} (`{member}`)",
            f"Likely source: `{invite['source_slug'] if invite and invite['source_slug'] else 'unknown'}`",
            f"Source type: `{invite['source_type'] if invite else 'unknown'}`",
            f"Invite code: `{match.code or 'unknown'}`",
        ]
        if invite and invite["source_type"] == "user-created":
            lines.append(f"Member invite creator: {invite['inviter_name'] or 'unknown'}")
        elif invite and invite["source_type"] in {"managed", "attached"}:
            lines.append(
                "HCM source created/attached by: "
                f"{invite['source_created_by_name'] or 'configuration/bootstrap'}"
            )
            if (
                invite["inviter_name"]
                and invite["inviter_name"] != invite["source_created_by_name"]
            ):
                lines.append(f"Discord invite creator: {invite['inviter_name']}")
        elif invite:
            lines.append(f"Invite creator: {invite['inviter_name'] or 'unknown'}")
        lines.extend(
            [
                f"Confidence: `{match.confidence}`",
                f"Reason: {match.reason}",
                f"Account created: {member.created_at.strftime('%Y-%m-%d')}",
                f"Joined: {(member.joined_at or datetime.now(UTC)).strftime('%Y-%m-%d %H:%M UTC')}",
            ]
        )
        await self.send_log("\n".join(lines))

    async def send_log(self, message: str) -> None:
        if not self.settings.log_channel_id:
            LOG.info("Discord log channel disabled: %s", message.replace("\n", " | "))
            return
        channel = self.get_channel(self.settings.log_channel_id)
        if not isinstance(channel, discord.abc.Messageable):
            LOG.error("LOG_CHANNEL_ID does not resolve to a messageable channel")
            return
        try:
            await channel.send(message, allowed_mentions=discord.AllowedMentions(users=True))
        except discord.HTTPException:
            LOG.exception("Could not send join log")

    async def fetch_invite_snapshots(
        self, guild: discord.Guild
    ) -> dict[str, InviteSnapshot]:
        invites = await guild.invites()
        return {invite.code: snapshot_from_discord(invite) for invite in invites}

    async def refresh_invites(self, guild: discord.Guild, *, bootstrap: bool = False) -> None:
        try:
            current = await self.fetch_invite_snapshots(guild)
        except discord.Forbidden:
            LOG.error("Missing Manage Server permission; cannot read invite-use metadata")
            return
        except discord.HTTPException:
            LOG.exception("Discord invite refresh failed")
            return
        self._sync_invites_to_db(guild.id, current)
        if bootstrap:
            self._attach_catalog_preferred_codes(current)
        self.invite_cache = current
        write_website_mapping(self.db, self.settings.website_export_path)

    def _sync_invites_to_db(
        self, guild_id: int, snapshots: dict[str, InviteSnapshot]
    ) -> None:
        self.db.mark_all_invites_inactive(guild_id)
        bot_id = str(self.user.id) if self.user else None
        for snapshot in snapshots.values():
            existing = self.db.get_invite(snapshot.code)
            source_type = None
            source_slug = None
            if existing is None:
                if bot_id and snapshot.inviter_id == bot_id:
                    source_type = "unmapped-bot"
                else:
                    source_type = "user-created"
                    source_slug = "member-invite"
            self.db.upsert_invite(
                guild_id,
                snapshot,
                source_slug=source_slug,
                source_type=source_type,
            )

    def _attach_catalog_preferred_codes(
        self, snapshots: dict[str, InviteSnapshot]
    ) -> None:
        for source in self.catalog.sources:
            code = source.preferred_invite_code
            if not code or code not in snapshots:
                continue
            existing = self.db.invite_for_source(source.slug)
            if existing and existing["code"] == code:
                continue
            self.db.map_invite(
                code,
                source.slug,
                "attached",
                None,
                "configuration/bootstrap",
            )

    @tasks.loop(seconds=600)
    async def refresh_loop(self) -> None:
        guild = self.get_guild(self.settings.guild_id)
        if guild:
            await self.refresh_invites(guild)

    @refresh_loop.before_loop
    async def before_refresh_loop(self) -> None:
        await self.wait_until_ready()

    @tasks.loop(hours=24)
    async def maintenance_loop(self) -> None:
        purged = self.db.purge_identities(self.settings.identity_retention_days)
        backup = self.db.backup(self.settings.backup_dir, self.settings.backup_keep)
        LOG.info("Maintenance complete: purged=%s backup=%s", purged, backup)

    @maintenance_loop.before_loop
    async def before_maintenance_loop(self) -> None:
        await self.wait_until_ready()
