from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class InviteSnapshot:
    code: str
    uses: int
    max_uses: int = 0
    max_age: int = 0
    temporary: bool = False
    channel_id: str | None = None
    channel_name: str | None = None
    inviter_id: str | None = None
    inviter_name: str | None = None
    created_at: str | None = None
    expires_at: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "uses": self.uses,
            "max_uses": self.max_uses,
            "max_age": self.max_age,
            "temporary": self.temporary,
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "inviter_id": self.inviter_id,
            "inviter_name": self.inviter_name,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True, slots=True)
class InviteMatch:
    code: str | None
    confidence: str
    reason: str
    deltas: dict[str, int]


def match_used_invite(
    previous: Mapping[str, InviteSnapshot],
    current: Mapping[str, InviteSnapshot],
) -> InviteMatch:
    """Infer which invite was used by comparing invite-use counters.

    Discord does not include the invite code in the member-join event. A disappearing
    one-use invite is treated as consumed only when it was exactly one use short of
    its configured maximum in the previous snapshot.
    """

    deltas: dict[str, int] = {}
    reasons: dict[str, str] = {}

    newly_observed: set[str] = set()

    for code, old in previous.items():
        new = current.get(code)
        if new is not None:
            delta = new.uses - old.uses
            if delta > 0:
                deltas[code] = delta
                reasons[code] = "invite use counter increased"
            continue

        # Discord removes a finite-use invite after its last allowed use. Do not
        # infer consumption for an arbitrary deleted or expired invite.
        if old.max_uses > 0 and old.uses == old.max_uses - 1:
            deltas[code] = 1
            reasons[code] = "one-use remainder disappeared after join"

    # A member-created invite can be created and used between periodic snapshots.
    # Keep the candidate code, but lower confidence because there was no baseline.
    for code, new in current.items():
        if code not in previous and new.uses > 0:
            deltas[code] = new.uses
            reasons[code] = "newly observed invite already had one or more uses"
            newly_observed.add(code)

    if len(deltas) == 1:
        code = next(iter(deltas))
        delta = deltas[code]
        if code in newly_observed:
            return InviteMatch(code, "ambiguous", reasons[code], deltas)
        if delta == 1:
            return InviteMatch(code, "normal", reasons[code], deltas)
        return InviteMatch(
            code,
            "ambiguous",
            f"one invite increased by {delta}; multiple joins may have been coalesced",
            deltas,
        )

    if len(deltas) > 1:
        return InviteMatch(
            None,
            "ambiguous",
            "multiple invite counters changed during the same comparison window",
            deltas,
        )

    return InviteMatch(
        None,
        "unknown",
        "no invite counter change was visible",
        {},
    )
