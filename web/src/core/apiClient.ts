const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

const ACCESS_TOKEN_KEY = "zonovia.access_token";
const REFRESH_TOKEN_KEY = "zonovia.refresh_token";

export interface ApiErrorBody {
  code: string;
  message: string;
  field_errors?: Record<string, unknown> | null;
}

export class ApiError extends Error {
  code: string;
  status: number;
  fieldErrors?: Record<string, unknown> | null;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.fieldErrors = body.field_errors;
  }
}

export interface Envelope<T> {
  data: T;
  meta: { page: number; page_size: number; total: number } | null;
  error: ApiErrorBody | null;
}

export const tokenStore = {
  getAccessToken: () => localStorage.getItem(ACCESS_TOKEN_KEY),
  getRefreshToken: () => localStorage.getItem(REFRESH_TOKEN_KEY),
  setTokens: (accessToken: string, refreshToken: string) => {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  },
  clear: () => {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  },
};

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = tokenStore.getRefreshToken();
  if (!refreshToken) return null;

  if (!refreshPromise) {
    refreshPromise = fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
      .then(async (res) => {
        if (!res.ok) return null;
        const body = (await res.json()) as Envelope<{ access_token: string; refresh_token: string }>;
        if (!body.data) return null;
        tokenStore.setTokens(body.data.access_token, body.data.refresh_token);
        return body.data.access_token;
      })
      .catch(() => null)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

interface RequestOptions {
  method?: string;
  params?: Record<string, string | number | boolean | undefined>;
  body?: unknown;
  skipAuth?: boolean;
}

function buildUrl(path: string, params?: RequestOptions["params"]): string {
  const url = new URL(`${API_BASE_URL}${path}`);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function rawRequest(path: string, options: RequestOptions, accessToken: string | null): Promise<Response> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (accessToken && !options.skipAuth) headers.Authorization = `Bearer ${accessToken}`;

  return fetch(buildUrl(path, options.params), {
    method: options.method ?? "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let accessToken = tokenStore.getAccessToken();
  let res = await rawRequest(path, options, accessToken);

  if (res.status === 401 && !options.skipAuth && tokenStore.getRefreshToken()) {
    accessToken = await refreshAccessToken();
    if (accessToken) {
      res = await rawRequest(path, options, accessToken);
    }
  }

  if (res.status === 204) return undefined as T;

  const body = (await res.json()) as Envelope<T>;
  if (!res.ok || body.error) {
    if (res.status === 401) tokenStore.clear();
    throw new ApiError(res.status, body.error ?? { code: "UNKNOWN", message: "Something went wrong." });
  }
  return body.data;
}

export async function apiRequestWithMeta<T>(path: string, options: RequestOptions = {}): Promise<Envelope<T>> {
  let accessToken = tokenStore.getAccessToken();
  let res = await rawRequest(path, options, accessToken);

  if (res.status === 401 && !options.skipAuth && tokenStore.getRefreshToken()) {
    accessToken = await refreshAccessToken();
    if (accessToken) {
      res = await rawRequest(path, options, accessToken);
    }
  }

  const body = (await res.json()) as Envelope<T>;
  if (!res.ok || body.error) {
    if (res.status === 401) tokenStore.clear();
    throw new ApiError(res.status, body.error ?? { code: "UNKNOWN", message: "Something went wrong." });
  }
  return body;
}

export const api = {
  get: <T>(path: string, params?: RequestOptions["params"]) => apiRequest<T>(path, { method: "GET", params }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) => apiRequest<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "PATCH", body }),
  put: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "PUT", body }),
  delete: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "DELETE", body }),
};

/** Downloads a file endpoint that requires the Bearer token — a plain <a href> can't attach an
 * Authorization header, so this fetches the bytes and triggers a save via a throwaway object
 * URL. Non-JSON responses don't go through apiRequest's envelope parsing. Not used by any page
 * yet (no export/report endpoints in this phase) but kept for fidelity with the ported client. */
export async function downloadFile(path: string, params: Record<string, string | number | boolean | undefined>): Promise<void> {
  const accessToken = tokenStore.getAccessToken();
  const url = new URL(`${API_BASE_URL}${path}`);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) url.searchParams.set(key, String(value));
  }
  const res = await fetch(url.toString(), { headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {} });
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as Envelope<unknown> | null;
    throw new ApiError(res.status, body?.error ?? { code: "UNKNOWN", message: "Download failed." });
  }
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const filenameMatch = /filename="?([^";]+)"?/.exec(disposition);
  const filename = filenameMatch?.[1] ?? "download";
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}
