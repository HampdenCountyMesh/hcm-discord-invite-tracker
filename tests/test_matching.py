from hcm_invite_tracker.matching import InviteSnapshot, match_used_invite


def snap(code: str, uses: int, max_uses: int = 0) -> InviteSnapshot:
    return InviteSnapshot(code=code, uses=uses, max_uses=max_uses)


def test_single_increment_is_normal():
    result = match_used_invite({"a": snap("a", 4)}, {"a": snap("a", 5)})
    assert result.code == "a"
    assert result.confidence == "normal"


def test_multiple_changed_invites_are_ambiguous():
    result = match_used_invite(
        {"a": snap("a", 1), "b": snap("b", 3)},
        {"a": snap("a", 2), "b": snap("b", 4)},
    )
    assert result.code is None
    assert result.confidence == "ambiguous"


def test_consumed_final_use_invite_is_detected():
    result = match_used_invite({"a": snap("a", 0, max_uses=1)}, {})
    assert result.code == "a"
    assert result.confidence == "normal"


def test_arbitrarily_deleted_unlimited_invite_is_not_treated_as_used():
    result = match_used_invite({"a": snap("a", 3, max_uses=0)}, {})
    assert result.code is None
    assert result.confidence == "unknown"


def test_counter_jump_is_ambiguous():
    result = match_used_invite({"a": snap("a", 1)}, {"a": snap("a", 3)})
    assert result.code == "a"
    assert result.confidence == "ambiguous"


def test_newly_observed_used_invite_keeps_candidate_with_lower_confidence():
    result = match_used_invite({}, {"new": snap("new", 1)})
    assert result.code == "new"
    assert result.confidence == "ambiguous"
