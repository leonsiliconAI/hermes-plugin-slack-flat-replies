interface SlackEvent {
  user?: string;
  thread_ts?: string;
  _hermes_reaction?: boolean;
  _hermes_force_process?: boolean;
}

/** The adapter owns bot classification, including its profile-scoped allowlist. */
export function shouldReplyFlat(
  event: SlackEvent,
  ts: string,
  isDm: boolean,
  isBot: () => boolean,
): boolean {
  if (isDm || !event.user || event._hermes_reaction || event._hermes_force_process) return false;
  return (!event.thread_ts || event.thread_ts === ts) && !isBot();
}
