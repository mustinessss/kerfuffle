import { UserManager, WebStorageStateStore } from "oidc-client-ts";
import type { User } from "oidc-client-ts";

const authority = import.meta.env.VITE_OIDC_AUTHORITY;
const clientId = import.meta.env.VITE_OIDC_CLIENT_ID;
export const oidcConfigured = Boolean(authority && clientId);

export const userManager = oidcConfigured
  ? new UserManager({
      authority,
      client_id: clientId,
      redirect_uri: `${window.location.origin}/auth/callback`,
      post_logout_redirect_uri: `${window.location.origin}/`,
      response_type: "code",
      scope: "openid profile email",
      automaticSilentRenew: true,
      userStore: new WebStorageStateStore({ store: window.sessionStorage }),
      stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
    })
  : null;

let callbackPromise: Promise<User | undefined> | null = null;

export function completeSigninCallback(): Promise<User | undefined> {
  if (!userManager) return Promise.resolve(undefined);
  if (!callbackPromise) callbackPromise = userManager.signinCallback();
  return callbackPromise;
}
