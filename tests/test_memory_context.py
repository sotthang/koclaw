from koclaw.core.memory_context import parse_memory_context


class TestParseMemoryContext:
    # ── Slack ──────────────────────────────────────────────────────────────

    def test_slack_dm_yields_user_scope(self):
        ctx = parse_memory_context("slack:D001", user_id="U123")
        assert ctx.user_scope == "U123"
        assert ctx.channel_scope is None
        assert ctx.thread_scope is None

    def test_slack_dm_without_user_id_yields_no_scope(self):
        ctx = parse_memory_context("slack:D001", user_id=None)
        assert ctx.user_scope is None

    def test_slack_channel_yields_channel_scope(self):
        ctx = parse_memory_context("slack:C001", user_id="U123")
        assert ctx.user_scope is None
        assert ctx.channel_scope == "slack:C001"
        assert ctx.thread_scope is None

    def test_slack_thread_yields_channel_and_thread_scope(self):
        ctx = parse_memory_context("slack:C001:9999.0000", user_id="U123")
        assert ctx.user_scope is None
        assert ctx.channel_scope == "slack:C001"
        assert ctx.thread_scope == "slack:C001:9999.0000"

    # ── Discord ────────────────────────────────────────────────────────────

    def test_discord_dm_yields_user_scope(self):
        ctx = parse_memory_context("discord:dm:123", user_id="123")
        assert ctx.user_scope == "123"
        assert ctx.channel_scope is None
        assert ctx.thread_scope is None

    def test_discord_channel_yields_channel_scope(self):
        ctx = parse_memory_context("discord:42", user_id="123")
        assert ctx.user_scope is None
        assert ctx.channel_scope == "discord:42"
        assert ctx.thread_scope is None

    def test_discord_thread_yields_channel_and_thread_scope(self):
        ctx = parse_memory_context("discord:thread:77", user_id="123", parent_channel_id="42")
        assert ctx.user_scope is None
        assert ctx.channel_scope == "discord:42"
        assert ctx.thread_scope == "discord:thread:77"

    def test_discord_thread_without_parent_yields_only_thread_scope(self):
        ctx = parse_memory_context("discord:thread:77", user_id="123")
        assert ctx.channel_scope is None
        assert ctx.thread_scope == "discord:thread:77"

    # ── applicable_scopes helper ───────────────────────────────────────────

    def test_applicable_scopes_for_dm(self):
        ctx = parse_memory_context("slack:D001", user_id="U1")
        assert ctx.applicable_scopes() == [("user", "U1")]

    def test_applicable_scopes_for_channel(self):
        ctx = parse_memory_context("slack:C001", user_id="U1")
        assert ctx.applicable_scopes() == [("channel", "slack:C001")]

    def test_applicable_scopes_for_thread(self):
        ctx = parse_memory_context("slack:C001:ts", user_id="U1")
        scopes = ctx.applicable_scopes()
        assert ("channel", "slack:C001") in scopes
        assert ("thread", "slack:C001:ts") in scopes
