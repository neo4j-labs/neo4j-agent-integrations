import { eveChannel } from "eve/channels/eve";
import { localDev, placeholderAuth, vercelOidc } from "eve/channels/auth";

/**
 * Route auth decides who reaches the agent — and, because the memory scope is
 * derived from `ctx.session.auth`, it is also what separates one user's memory
 * from another's. See `agent/lib/scope.ts`.
 *
 * Before a browser calls this in production, replace `placeholderAuth()` with
 * your app's authenticator, returning `principalType: "user"` and a stable
 * `principalId`. That id becomes the NAMS user id:
 *
 *   function appSession(): AuthFn<Request> {
 *     return async (request) => {
 *       const session = await getSession(request);
 *       if (!session) return null;
 *       return {
 *         authenticator: "app",
 *         principalId: session.userId,   // ← stable per person; becomes the NAMS user id
 *         principalType: "user",
 *         attributes: { email: session.email },
 *       };
 *     };
 *   }
 *
 *   export default eveChannel({ auth: [appSession(), vercelOidc(), localDev()] });
 *
 * Until then, `DEMO_USER_ID` in `.env.local` gives local development a stable
 * memory scope across `eve dev` restarts.
 */
export default eveChannel({
  auth: [
    // Lets the eve TUI and your Vercel deployments reach the deployed agent.
    vercelOidc(),
    // Open on localhost for `eve dev` and the REPL; ignored in production.
    localDev(),
    // Rejects browser requests in production until you replace it.
    placeholderAuth(),
  ],
});
