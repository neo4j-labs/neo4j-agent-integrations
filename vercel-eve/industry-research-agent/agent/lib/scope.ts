/**
 * Who the memory belongs to.
 *
 * The memory scope is derived from verified session context only. No tool
 * accepts a `userId` argument, so the model cannot address another user's
 * memory by inventing an id — the classic multi-tenant memory failure.
 */
import type { SessionAuth } from "eve/context";
import type { NamsScope } from "./nams";

/** The subset of `ctx` every eve callback shares — tools, hooks, and dynamic resolvers alike. */
export interface ScopeSource {
  readonly session: {
    readonly id: string;
    readonly auth: SessionAuth;
  };
}

/**
 * Resolve the NAMS user id for the active turn.
 *
 * Precedence:
 *   1. the authenticated caller of this turn (`auth.current`)
 *   2. the caller that started the session (`auth.initiator`)
 *   3. `DEMO_USER_ID`, so `eve dev` recalls across restarts without auth
 *   4. the eve session id, which scopes memory to this session only
 *
 * Steps 3 and 4 exist for local development. In production, put a real
 * authenticator in `agent/channels/eve.ts` so step 1 always wins — see
 * https://vercel.com/docs/eve/guides/auth-and-route-protection.
 */
export function memoryScope(ctx: ScopeSource): NamsScope {
  const principal = ctx.session.auth.current ?? ctx.session.auth.initiator;

  if (principal?.principalType === "user" && principal.principalId) {
    return { userId: principal.principalId };
  }

  const demoUserId = process.env.DEMO_USER_ID?.trim();
  if (demoUserId) return { userId: demoUserId };

  return { userId: `eve-session:${ctx.session.id}` };
}

/** True when the scope came from a real authenticated user rather than a dev fallback. */
export function isAuthenticatedScope(ctx: ScopeSource): boolean {
  return ctx.session.auth.current?.principalType === "user";
}
