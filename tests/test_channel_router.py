from koclaw.channels import match_registry, parse_parent_session_id


def test_matches_exact_prefix():
    registry = {"discord:": "discord_fn", "": "slack_fn"}
    assert match_registry(registry, "discord:42") == "discord_fn"


def test_matches_default_prefix():
    registry = {"discord:": "discord_fn", "": "slack_fn"}
    assert match_registry(registry, "C123456") == "slack_fn"


def test_longer_prefix_wins():
    registry = {"discord:dm:": "dm_fn", "discord:": "discord_fn", "": "slack_fn"}
    assert match_registry(registry, "discord:dm:123") == "dm_fn"
    assert match_registry(registry, "discord:456") == "discord_fn"


def test_returns_none_when_no_match():
    registry = {"discord:": "discord_fn"}
    assert match_registry(registry, "C123456") is None


def test_empty_registry_returns_none():
    assert match_registry({}, "anything") is None


# ── parse_parent_session_id ────────────────────────────────────────────────────

def test_slack_thread_parent_is_channel():
    assert parse_parent_session_id("slack:C123:1234.5") == "slack:C123"


def test_discord_thread_parent_is_channel():
    assert parse_parent_session_id("discord:thread:P123:T456") == "discord:P123"


def test_slack_channel_has_no_parent():
    assert parse_parent_session_id("slack:C123") is None


def test_slack_dm_has_no_parent():
    assert parse_parent_session_id("slack:dm:U001") is None


def test_discord_channel_has_no_parent():
    assert parse_parent_session_id("discord:42") is None


def test_discord_dm_has_no_parent():
    assert parse_parent_session_id("discord:dm:123") is None
