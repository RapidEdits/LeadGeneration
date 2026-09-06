"""Email subsystem (Phase 3): providers, tracking, sending, inbound polling.

The `EmailProvider` interface is the seam where Gmail / Microsoft Graph / SMTP plug
in uniformly. `sender.send_campaign_message` is the single email send path the engine
calls; it renders tracking + unsubscribe into the message before handing it to a
provider resolved from the workspace's connected account.
"""
