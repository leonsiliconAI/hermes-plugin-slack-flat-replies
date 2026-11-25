"""Run against a Hermes checkout with its environment (see README): it drives the real Slack adapter."""

from __future__ import annotations

import importlib.util
import sys
import pathlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import PlatformConfig
from gateway.platforms.base import _reply_anchor_for_event, _thread_metadata_for_source
from plugins.platforms.slack.adapter import SlackAdapter

_HERE = pathlib.Path(__file__).resolve().parents[1]


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


plugin = _load("slack_flat_replies", _HERE / "__init__.py")
autolinear = _load("autolinear", _HERE.parent / "hermes-plugin-autolinear" / "__init__.py")

LEON, BOT = "U0LEON00001", "U_BOT"
CHANNEL, DM, NEW = "C0ISSUE0001", "D0LEONDM01", "C0NEWISSUE"
CHANNELS = {
    CHANNEL: {"id": CHANNEL, "name": "leon-427-testing-autolinear"},
    NEW: {"id": NEW, "name": "leon-428-check-rogers"},
    DM: {"id": DM, "is_im": True, "user": LEON},
}


@pytest.fixture()
def adapter(monkeypatch):
    monkeypatch.setenv("SLACK_REQUIRE_MENTION", "false")
    a = SlackAdapter(PlatformConfig(enabled=True, token="***"))
    a._app = MagicMock()
    a._app.client = AsyncMock()
    a._app.client.users_info = AsyncMock(
        return_value={"ok": True, "user": {"is_bot": False, "profile": {"display_name": "Leon"}}})

    async def info(channel, **_):
        return {"ok": True, "channel": CHANNELS[channel]}

    a._app.client.conversations_info = AsyncMock(side_effect=info)
    a._app.client.conversations_replies = AsyncMock(return_value={"ok": True, "messages": []})
    a._app.client.chat_postMessage = AsyncMock(return_value={"ok": True, "ts": "1794000009.000001"})
    a._bot_user_id = BOT
    a._running = True
    a.handle_message = AsyncMock()
    return a


def _message(ts: str, channel: str = CHANNEL, **extra) -> dict:
    kind = "im" if channel.startswith("D") else "group"
    return {"type": "message", "text": "what did Rogers bill me?", "user": LEON, "channel": channel,
            "channel_type": kind, "ts": ts, "client_msg_id": f"6a1c7d1e-0000-4000-8000-{ts[-6:]}000000",
            **extra}


def _turns(adapter):
    return [call.args[0] for call in adapter.handle_message.await_args_list]


async def _reply_thread(adapter, turn) -> str | None:
    """Sends a reply the way the gateway does and returns the thread_ts Slack was given."""
    adapter._app.client.chat_postMessage.reset_mock()
    await adapter.send(turn.source.chat_id, "ok", reply_to=_reply_anchor_for_event(turn),
                       metadata=_thread_metadata_for_source(turn.source))
    return adapter._app.client.chat_postMessage.await_args.kwargs.get("thread_ts")


@pytest.mark.asyncio
async def test_stock_hermes_replies_in_a_thread(adapter):
    """Pins the upstream behaviour this plugin changes."""
    await adapter._handle_slack_message(_message("1794000000.000001"))
    turn = _turns(adapter)[0]
    assert turn.source.thread_id == "1794000000.000001"
    assert await _reply_thread(adapter, turn) == "1794000000.000001"


@pytest.mark.asyncio
async def test_a_top_level_message_is_answered_in_the_channel_in_one_conversation(adapter):
    plugin.wire(None, adapter)
    await adapter._handle_slack_message(_message("1794000000.000002"))
    await adapter._handle_slack_message(_message("1794000000.000003"))
    first, second = _turns(adapter)
    for turn in (first, second):
        assert turn.source.thread_id is None, "the channel's session, not a thread's"
        assert turn.raw_message[plugin.FLAG] is True
        assert _reply_anchor_for_event(turn) is None
        assert await _reply_thread(adapter, turn) is None, "posted in the channel"
    assert first.source.chat_id == second.source.chat_id == CHANNEL


@pytest.mark.asyncio
async def test_a_message_in_a_thread_is_answered_in_that_thread(adapter):
    plugin.wire(None, adapter)
    root = "1794000000.000010"
    await adapter._handle_slack_message(_message("1794000000.000011", thread_ts=root))
    turn = _turns(adapter)[0]
    assert turn.source.thread_id == root
    assert plugin.FLAG not in turn.raw_message
    assert await _reply_thread(adapter, turn) == root


def test_bots_dms_and_reaction_turns_keep_their_threads(adapter):
    plugin.wire(None, adapter)
    ts = "1794000000.000020"
    bot = _message(ts, bot_id="B0LINEARSY", text=f"<@{BOT}> LEON-9 is now Awaiting Hermes")
    assert adapter._session_thread_ts(bot, ts, False, {}) == ts
    dm = _message(ts, channel=DM)
    assert adapter._session_thread_ts(dm, ts, True, {}) == ts
    reaction = _message(ts, _hermes_reaction=True)
    assert adapter._session_thread_ts(reaction, ts, False, {}) == ts
    assert not any(plugin.FLAG in e for e in (bot, dm, reaction))


@pytest.mark.parametrize("flat_first", [True, False])
@pytest.mark.parametrize("task_progress_enabled", [True, False])
@pytest.mark.asyncio
async def test_autolinear_reply_uses_the_moved_issue_context(
    adapter, monkeypatch, tmp_path, flat_first, task_progress_enabled,
):
    monkeypatch.setenv(autolinear.TOKEN_ENV, "t")
    monkeypatch.setenv(autolinear.USER_ENV, LEON)
    monkeypatch.setattr(autolinear, "_post_json", lambda *a: (200, {
        "ok": True, "issue": {"id": "i", "identifier": "LEON-428", "url": "https://linear.app/x"},
        "channel": {"id": NEW, "name": "leon-428-check-rogers"}, "ts": "1794000001.000001",
        "source": "a DM with Hermes"}))
    team = "T0WORKSPACE"
    root = "1794000009.000001"
    client = adapter._app.client
    adapter._team_clients[team] = client
    client.chat_postMessage.return_value = {"ok": True, "channel": NEW, "ts": root}
    handlers = [plugin.wire, autolinear.wire]
    if task_progress_enabled:
        muse = _load("hermes22muse_flat_replies", _HERE.parent / "hermes-plugin-hermes22muse" / "__init__.py")
        monkeypatch.setattr(muse.Relay, "run", AsyncMock())
        monkeypatch.setattr(adapter, "disconnect", AsyncMock())
        import hermes_constants

        monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: tmp_path)
        monkeypatch.setenv("HERMES22MUSE_SLACK_USER_ID", LEON)
        monkeypatch.setenv("HERMES22MUSE_MCP_URL", "http://127.0.0.1:7899/mcp")
        monkeypatch.setenv("HERMES22MUSE_MCP_SECRET", "x" * 32)
        muse.register(SimpleNamespace(register_tool=lambda **_: None, register_hook=lambda *_: None,
                                      register_platform_handler=lambda _, wire: handlers.append(wire)))
    try:
        for wire in (handlers if flat_first else reversed(handlers)):
            wire(None, adapter)
        await adapter._handle_slack_message(_message("1794000000.000030", channel=DM, team=team))
        turn, = _turns(adapter)
        assert turn.source.chat_id == NEW and turn.message_id == "1794000001.000001"
        expected_thread = root if task_progress_enabled else None
        assert turn.source.thread_id == expected_thread
        if task_progress_enabled:
            client.chat_postMessage.assert_awaited_once()
            assert client.chat_postMessage.await_args.kwargs["channel"] == NEW
            assert "thread_ts" not in client.chat_postMessage.await_args.kwargs
        else:
            client.chat_postMessage.assert_not_awaited()
        assert await _reply_thread(adapter, turn) == expected_thread
    finally:
        if task_progress_enabled:
            await adapter.disconnect()


def test_wire_is_idempotent(adapter):
    plugin.wire(None, adapter)
    patched = adapter._session_thread_ts
    plugin.wire(None, adapter)
    assert adapter._session_thread_ts is patched


def test_missing_internals_fail_closed(caplog):
    class Bare:
        pass

    bare = Bare()
    plugin.wire(None, bare)
    assert not hasattr(bare, "_session_thread_ts")
    assert "internals changed" in caplog.text
