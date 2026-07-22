from __future__ import annotations

import io
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from .discord_helpers import extract_invite_code, snapshot_from_discord
from .website import render_website_mapping, write_website_mapping

if TYPE_CHECKING:
    from .bot import InviteTrackerBot


class TrackerPermissionMixin:
    def __init__(self, bot: InviteTrackerBot):
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        member = interaction.user
        if not isinstance(member, discord.Member):
            await _ephemeral(interaction, "This command only works inside the configured server.")
            return False
        if member.guild_permissions.manage_guild or member.guild_permissions.administrator:
            return True
        role_ids = {role.id for role in member.roles}
        if role_ids & self.bot.settings.admin_role_ids:
            return True
        await _ephemeral(interaction, "You do not have permission to manage invite sources.")
        return False


class SourceCommands(TrackerPermissionMixin, commands.GroupCog, group_name="source"):
    """Manage source-specific invite mappings."""

    @app_commands.command(name="list", description="List configured sources and invite mappings")
    async def list_sources(self, interaction: discord.Interaction) -> None:
        rows = self.bot.db.list_sources_with_invites()
        lines = []
        for row in rows:
            code = row["code"] or "not provisioned"
            lines.append(f"`{row['slug']}` → `{code}` ({row['source_type'] or 'none'})")
        await interaction.response.send_message("\n".join(lines)[:1900], ephemeral=True)

    @app_commands.command(
        name="provision", description="Create a permanent invite for one configured source"
    )
    @app_commands.describe(source="Configured source slug", channel="Invite destination channel")
    async def provision(
        self,
        interaction: discord.Interaction,
        source: str,
        channel: discord.TextChannel | None = None,
    ) -> None:
        definition = self.bot.catalog.by_slug(source)
        if not definition:
            await interaction.response.send_message("Unknown source slug.", ephemeral=True)
            return
        existing = self.bot.db.invite_for_source(source)
        if existing:
            await interaction.response.send_message(
                f"`{source}` already maps to `https://discord.gg/{existing['code']}`.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        target = channel or await self._default_channel(interaction)
        if target is None:
            await interaction.followup.send(
                "Choose a text channel or set DEFAULT_INVITE_CHANNEL_ID.", ephemeral=True
            )
            return
        try:
            invite = await target.create_invite(
                max_age=0,
                max_uses=0,
                temporary=False,
                unique=True,
                reason=f"Invite source provisioned: {source} by {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Discord denied invite creation. Check Create Invite permission in that channel.",
                ephemeral=True,
            )
            return
        snapshot = snapshot_from_discord(invite)
        self.bot.db.upsert_invite(
            interaction.guild_id or self.bot.settings.guild_id,
            snapshot,
            source_slug=source,
            source_type="managed",
            source_created_by_id=str(interaction.user.id),
            source_created_by_name=str(interaction.user),
        )
        self.bot.invite_cache[invite.code] = snapshot
        write_website_mapping(self.bot.db, self.bot.settings.website_export_path)
        await interaction.followup.send(
            f"Created `{source}`: {invite.url}", ephemeral=True
        )

    @app_commands.command(
        name="provision-all",
        description="Create permanent invites for every unprovisioned configured source",
    )
    @app_commands.describe(confirm="Type CREATE to authorize the batch")
    async def provision_all(self, interaction: discord.Interaction, confirm: str) -> None:
        if confirm != "CREATE":
            await interaction.response.send_message(
                "No invites created. Run again with `confirm: CREATE`.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        target = await self._default_channel(interaction)
        if target is None:
            await interaction.followup.send(
                "Set DEFAULT_INVITE_CHANNEL_ID before provisioning all sources.",
                ephemeral=True,
            )
            return
        created: list[str] = []
        skipped: list[str] = []
        for definition in self.bot.catalog.sources:
            if not definition.provision or self.bot.db.invite_for_source(definition.slug):
                skipped.append(definition.slug)
                continue
            try:
                invite = await target.create_invite(
                    max_age=0,
                    max_uses=0,
                    temporary=False,
                    unique=True,
                    reason=(
                        f"Invite source provisioned: {definition.slug} by {interaction.user}"
                    ),
                )
            except discord.HTTPException as exc:
                await interaction.followup.send(
                    f"Stopped after Discord error while creating `{definition.slug}`: {exc}",
                    ephemeral=True,
                )
                break
            snapshot = snapshot_from_discord(invite)
            self.bot.db.upsert_invite(
                interaction.guild_id or self.bot.settings.guild_id,
                snapshot,
                source_slug=definition.slug,
                source_type="managed",
                source_created_by_id=str(interaction.user.id),
                source_created_by_name=str(interaction.user),
            )
            self.bot.invite_cache[invite.code] = snapshot
            created.append(definition.slug)
        write_website_mapping(self.bot.db, self.bot.settings.website_export_path)
        await interaction.followup.send(
            f"Created: {', '.join(created) or 'none'}\nSkipped: {', '.join(skipped) or 'none'}",
            ephemeral=True,
        )

    @app_commands.command(
        name="attach", description="Attach an existing Discord invite to a configured source"
    )
    async def attach(
        self, interaction: discord.Interaction, source: str, invite: str
    ) -> None:
        if not self.bot.catalog.by_slug(source):
            await interaction.response.send_message("Unknown source slug.", ephemeral=True)
            return
        code = extract_invite_code(invite)
        if not code:
            await interaction.response.send_message(
                "That is not a valid invite code or URL.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        if guild is None:
            return
        await self.bot.refresh_invites(guild)
        row = self.bot.db.get_invite(code)
        if not row or not row["active"]:
            await interaction.followup.send(
                "The bot cannot see that invite in this server.", ephemeral=True
            )
            return
        self.bot.db.map_invite(
            code,
            source,
            "attached",
            str(interaction.user.id),
            str(interaction.user),
        )
        write_website_mapping(self.bot.db, self.bot.settings.website_export_path)
        await interaction.followup.send(
            f"Attached `{source}` to `https://discord.gg/{code}`.", ephemeral=True
        )

    @app_commands.command(
        name="refresh", description="Refresh invite counters and discover user-created invites"
    )
    async def refresh(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        if interaction.guild:
            await self.bot.refresh_invites(interaction.guild)
        await interaction.followup.send("Invite snapshot refreshed.", ephemeral=True)

    @app_commands.command(
        name="export", description="Download the current website source-to-invite mapping"
    )
    async def export(self, interaction: discord.Interaction) -> None:
        payload = render_website_mapping(self.bot.db).encode("utf-8")
        file = discord.File(io.BytesIO(payload), filename="discord-invites.yml")
        await interaction.response.send_message(file=file, ephemeral=True)

    async def _default_channel(
        self, interaction: discord.Interaction
    ) -> discord.TextChannel | None:
        channel_id = self.bot.settings.default_invite_channel_id
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if isinstance(channel, discord.TextChannel):
            return channel
        if isinstance(interaction.channel, discord.TextChannel):
            return interaction.channel
        return None


class ReportCommands(TrackerPermissionMixin, commands.GroupCog, group_name="report"):
    @app_commands.command(name="summary", description="Show join totals by invite source")
    async def summary(self, interaction: discord.Interaction) -> None:
        rows = self.bot.db.source_summary()
        if not rows:
            text = "No joins have been recorded yet."
        else:
            text = "\n".join(
                f"`{row['source_slug']}`: {row['join_count']} joins "
                f"({row['normal_count']} normal-confidence)"
                for row in rows
            )
        await interaction.response.send_message(text[:1900], ephemeral=True)

    @app_commands.command(name="recent", description="Show the most recently recorded joins")
    async def recent(self, interaction: discord.Interaction) -> None:
        rows = self.bot.db.recent_joins(15)
        if not rows:
            text = "No joins have been recorded yet."
        else:
            text = "\n".join(
                f"`{row['recorded_at'][:16]}` {row['member_name'] or '[purged]'} → "
                f"`{row['source_slug'] or 'unknown'}` ({row['confidence']})"
                for row in rows
            )
        await interaction.response.send_message(text[:1900], ephemeral=True)


async def _ephemeral(interaction: discord.Interaction, message: str) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)
