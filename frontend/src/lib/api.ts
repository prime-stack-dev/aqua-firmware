import type { MessageKey } from "./messages";
import type { TokenPair } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const ACCESS_KEY = "aqua.access";
const REFRESH_KEY = "aqua.refresh";

/** Skips login and shows sample data. Never active in a production build. */
export const IS_DEMO =
  process.env.NODE_ENV !== "production" && process.env.NEXT_PUBLIC_BYPASS_LOGIN === "true";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Which translated message describes this failure. */
export function errorKey(error: unknown): MessageKey {
  const status = error instanceof ApiError ? error.status : -1;
  if (status === 0) return "err_network";
  if (status >= 500) return "err_server";
  if (status === 403) return "err_forbidden";
  if (status === 404) return "err_notfound";
  if (status === 409) return "err_conflict";
  if (status === 422) return "err_invalid";
  return "err_generic";
}

// Stored per browser tab. A refresh token works only once, so two tabs sharing
// one could log the user out.
function saveTokens(tokens: TokenPair): void {
  sessionStorage.setItem(ACCESS_KEY, tokens.access_token);
  sessionStorage.setItem(REFRESH_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  sessionStorage.removeItem(ACCESS_KEY);
  sessionStorage.removeItem(REFRESH_KEY);
}

export function hasSession(): boolean {
  return IS_DEMO || sessionStorage.getItem(REFRESH_KEY) !== null;
}

async function send(path: string, init: RequestInit, token: string | null): Promise<Response> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  try {
    return await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check that the backend is running.");
  }
}

async function readError(response: Response): Promise<ApiError> {
  let detail: unknown;
  try {
    detail = (await response.json()).detail;
  } catch {
    detail = undefined;
  }
  const fallback = response.status >= 500 ? "The server had a problem." : "Request failed.";
  return new ApiError(response.status, typeof detail === "string" ? detail : fallback);
}

let refreshing: Promise<boolean> | null = null;

// Several requests can expire together, but only one may use the refresh token.
function refreshTokens(): Promise<boolean> {
  refreshing ??= (async () => {
    const refresh_token = sessionStorage.getItem(REFRESH_KEY);
    if (!refresh_token) return false;
    const response = await send(
      "/auth/refresh",
      { method: "POST", body: JSON.stringify({ refresh_token }) },
      null,
    );
    if (!response.ok) return false;
    saveTokens(await response.json());
    return true;
  })().finally(() => {
    refreshing = null;
  });
  return refreshing;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (IS_DEMO) {
    const { demoApi } = await import("./demo");
    return demoApi(path, init) as T;
  }
  let response = await send(path, init, sessionStorage.getItem(ACCESS_KEY));
  if (response.status === 401) {
    if (!(await refreshTokens())) {
      clearTokens();
      window.location.assign("/login");
      throw new ApiError(401, "Your session has ended. Please log in again.");
    }
    response = await send(path, init, sessionStorage.getItem(ACCESS_KEY));
  }
  if (!response.ok) throw await readError(response);
  return response.status === 204 ? (undefined as T) : response.json();
}

export async function login(
  email: string,
  password: string,
  organizationId?: string,
): Promise<void> {
  const response = await send(
    "/auth/login",
    {
      method: "POST",
      body: JSON.stringify({
        email,
        password,
        ...(organizationId ? { organization_id: organizationId } : {}),
      }),
    },
    null,
  );
  if (!response.ok) throw await readError(response);
  saveTokens(await response.json());
}

export async function logout(): Promise<void> {
  const refresh_token = sessionStorage.getItem(REFRESH_KEY);
  clearTokens();
  if (refresh_token) {
    // Leaving the page should not depend on the server answering.
    await send(
      "/auth/logout",
      { method: "POST", body: JSON.stringify({ refresh_token }) },
      null,
    ).catch(() => undefined);
  }
  window.location.assign("/login");
}
