"""Reply to a person's top-level Slack message at the top of the channel, not in a thread.

Leon's rule (2026-11-21): when he writes a message in a channel, Hermes answers in the channel itself
(as if "Also send to channel" were ticked), and only answers in a thread when he writes in that
thread. Stock Hermes (``reply_in_thread``, on by default) opens a thread under every top-level
message instead.

Hermes's Slack adapter already has a flat mode for single messages: an event carrying
``_hermes_no_thread_response`` (set for reaction handoffs) gets no session thread
(``_session_thread_ts`` returns its real thread, so none for a top-level message) and no reply
anchor (``_reply_anchor_for_event`` in the gateway), so its reply, its streamed drafts and its file
uploads all go to the channel. This plugin wraps ``_session_thread_ts`` on the live adapter and sets
that flag on top-level channel messages from people. With no thread, the session is the channel's,
so Hermes keeps one conversation per channel: an issue channel reads as one exchange.

Left as they were: thread replies (answered in their thread), DMs and group DMs, messages from bots
(slack22linear's pings, Gmail feed wake-ups), and reaction-triggered turns.

autolinear's plugin calls ``_session_thread_ts`` for the copy of Leon's message it moves into a new
issue channel, so that copy is answered at the top of the channel too, whichever plugin is wired
first. It fails closed: without the seams it relies on, it logs a warning and changes nothing.
"""

from __future__ import annotations

import functools
import logging

from ._bridge import call


logger = logging.getLogger(__name__)

_PATCHED_ATTR = "_slack_flat_replies_patched"
FLAG = "_hermes_no_thread_response"


def _flat(adapter, event, ts, is_dm) -> bool:
    """A top-level message from a person, in a channel."""
    return isinstance(event, dict) and call(
        __file__, "shouldReplyFlat", event, ts, is_dm,
        lambda: adapter._event_declares_bot_sender(event),
    )


def wire(native, adapter) -> None:
    """``register_platform_handler`` factory: patch this adapter instance once."""
    if getattr(adapter, _PATCHED_ATTR, False):
        return
    session_thread = getattr(adapter, "_session_thread_ts", None)
    is_bot = getattr(adapter, "_event_declares_bot_sender", None)
    if not (callable(session_thread) and callable(is_bot)):
        logger.warning(
            "slack-flat-replies: Slack adapter internals changed; Hermes keeps replying in threads")
        return

    @functools.wraps(session_thread)
    def session_thread_or_channel(event, ts, is_dm, assistant_meta, *args, **kwargs):
        try:
            if _flat(adapter, event, ts, is_dm):
                event[FLAG] = True
        except Exception:
            logger.warning("slack-flat-replies: could not check ts=%s", ts, exc_info=True)
        return session_thread(event, ts, is_dm, assistant_meta, *args, **kwargs)

    adapter._session_thread_ts = session_thread_or_channel
    setattr(adapter, _PATCHED_ATTR, True)
    logger.info(
        "slack-flat-replies: Hermes answers top-level channel messages in the channel, threads in "
        "their thread")


def register(ctx) -> None:
    ctx.register_platform_handler("slack", wire)
