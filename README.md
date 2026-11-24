# @-/com.leonsilicon.hermes.plugins.slack-flat-replies

Hermes plugin: when a person writes a top-level message in a Slack channel, Hermes answers at the top of the channel, not in a thread. It answers in a thread only when the message was written in that thread.

## Why

Leon's rule (2026-11-21): "always respond in a channel instead of as a thread unless I respond in that thread", as if Slack's "Also send to channel" were ticked. Stock Hermes (`reply_in_thread`, on by default) opens a thread under every top-level channel message, so in a new [autolinear](https://github.com/leonsilicon/leonsilicon.ai/blob/main/apps/hermes-plugin-autolinear/README.md) issue channel the answer hid in a thread under Leon's message.

## What it does

Hermes's Slack adapter already answers single events at the top of the channel: an event carrying `_hermes_no_thread_response` (set for reaction handoffs) gets no session thread and no reply anchor, so its reply, its streamed drafts and its uploads all go to the channel. The plugin wraps the live adapter's `_session_thread_ts` and sets that flag on top-level channel messages from people.

- **One conversation per channel.** With no thread, the session is the channel's, so each of Leon's top-level messages in an issue channel continues the same conversation.
- **Threads stay threads.** A message written in a thread is answered in that thread, in that thread's own session.
- **Left alone:** DMs and group DMs, messages from bots (slack22linear's pings, Gmail feed wake-ups) and reaction-triggered turns keep their threads, so unrelated notifications don't share one channel-wide session.

autolinear's plugin calls `_session_thread_ts` for the copy of Leon's message it moves into a new issue channel, so that copy is answered at the top of the channel too, whichever plugin is wired first. Without the seams it relies on, the plugin logs a warning and changes nothing; the whole-workspace alternative, `slack.extra.reply_in_thread: false`, would also flatten the bots' threads.

## Install

```sh
hermes plugins install leonsiliconAI/hermes-plugin-slack-flat-replies --enable --yes-deps
```

See [migration steps](https://github.com/leonsilicon/leonsilicon.ai/blob/main/DEVELOPMENT.md#hermes-plugin-mirrors) for an existing install. The plugin takes effect on the live adapter without a restart. The gateway log shows `slack-flat-replies: Hermes answers top-level channel messages in the channel, threads in their thread`.

## Test

The tests drive the real Slack adapter and the gateway's own reply-anchor and thread-metadata helpers, so they need a Hermes checkout's environment (Hermes Cloud ran v0.23.2 when this was written):

```sh
git -C ~/.hermes/hermes-agent worktree add --detach /tmp/hermes-v0.23.2 v0.23.2
cd /tmp/hermes-v0.23.2 && UV_PROJECT_ENVIRONMENT=/tmp/hermes-venv uv sync --frozen --extra slack
VIRTUAL_ENV=/tmp/hermes-venv uv pip install pytest pytest-asyncio
cd - && HERMES_HOME=$(mktemp -d) PYTHONPATH=/tmp/hermes-v0.23.2 /tmp/hermes-venv/bin/python -m pytest -q -p no:cacheprovider __tests__
```

One test pins the stock behaviour (a thread under every top-level message); another wires it with the autolinear plugin in both orders.
