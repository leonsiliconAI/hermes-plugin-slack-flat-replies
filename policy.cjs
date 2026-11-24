Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
// policy.ts
/** The adapter owns bot classification, including its profile-scoped allowlist. */
function shouldReplyFlat(event, ts, isDm, isBot) {
	if (isDm || !event.user || event._hermes_reaction || event._hermes_force_process) return false;
	return (!event.thread_ts || event.thread_ts === ts) && !isBot();
}
exports.shouldReplyFlat = shouldReplyFlat;
