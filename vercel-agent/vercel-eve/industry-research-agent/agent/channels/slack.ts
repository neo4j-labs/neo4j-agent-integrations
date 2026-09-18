import { slackChannel } from "eve/channels/slack";

// Slack channel using a direct Slack app (no Vercel Connect required).
// Credentials fall back to environment variables:
//   SLACK_BOT_TOKEN       - Bot User OAuth Token (xoxb-...), for outbound Web API calls
//   SLACK_SIGNING_SECRET  - App signing secret, to HMAC-verify inbound webhooks
// Set both in .env.local (local) and in the Vercel project env (production).
//
// In the Slack app: add bot scopes (app_mentions:read, chat:write, im:history,
// im:write, users:read), enable Event Subscriptions with Request URL
// https://<your-deployment>/eve/v1/slack, subscribe to bot events app_mention
// (and message.im for DMs), then install the app to the workspace.

export default slackChannel({
    credentials: {},
    threadContext: { since: "last-agent-reply" },
});