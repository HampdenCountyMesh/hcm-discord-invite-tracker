from __future__ import annotations

import re

import discord

from .matching import InviteSnapshot

_INVITE_CODE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord\.gg|discord(?:app)?\.com/invite)/([A-Za-z0-9-]+)|^([A-Za-z0-9-]+)$"
)


def snapshot_from_discord(invite: discord.Invite) -> InviteSnapshot:
    channel = invite.channel
    inviter = invite.inviter
    return InviteSnapshot(
        code=invite.code,
        uses=int(invite.uses or 0),
        max_uses=int(invite.max_uses or 0),
        max_age=int(invite.max_age or 0),
        temporary=bool(invite.temporary),
        channel_id=str(channel.id) if channel else None,
        channel_name=getattr(channel, "name", None),
        inviter_id=str(inviter.id) if inviter else None,
        inviter_name=str(inviter) if inviter else None,
        created_at=invite.created_at.isoformat() if invite.created_at else None,
        expires_at=invite.expires_at.isoformat() if invite.expires_at else None,
    )


def extract_invite_code(value: str) -> str | None:
    match = _INVITE_CODE_RE.fullmatch(value.strip())
    if not match:
        return None
    return match.group(1) or match.group(2)
