"""LinkedIn assisted-workflow subsystem (Phase 5).

LinkedIn has no compliant API for cold outreach, so live LinkedIn steps are not
sent over the wire. The engine parks each due LinkedIn message as a manual *task*
(a Message with status ``pending_action``, the member in ``awaiting_action``); a
human operator opens the lead's profile, sends the pre-personalized message on
LinkedIn, then confirms in-app. Replies are logged manually and run through the
same AI classification + sequence-halt path as email replies.

This keeps all outbound authorization in ``can_send`` and all sequence state in
the engine — the human is only the transport for a channel that forbids automation.
"""
