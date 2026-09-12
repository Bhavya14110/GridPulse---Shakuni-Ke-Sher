import type {
  HistoricalBacktest,
  PortfolioSummary,
  Site,
  SiteForecast,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      // The backend owns caching; asking the browser to cache on top of it just
      // makes "why is this stale" harder to answer during a demo.
      cache: "no-store",
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(
      `Can't reach the GridPulse API at ${API_BASE}. Is the backend running?`,
    );
  }

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    let detail = body;
    try {
      detail = JSON.parse(body).detail ?? body;
    } catch {
      /* body wasn't JSON; use it as-is */
    }
    throw new ApiError(detail || `Request failed (${response.status})`, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  portfolio: () => request<PortfolioSummary>("/api/portfolio/summary"),
  sites: () => request<Site[]>("/api/sites"),
  site: (id: number) => request<Site>(`/api/sites/${id}`),
  forecast: (id: number, hours = 72) =>
    request<SiteForecast>(`/api/sites/${id}/forecast?hours=${hours}`),
  historical: (id: number, days = 7) =>
    request<HistoricalBacktest>(`/api/sites/${id}/historical?days=${days}`),
  createSite: (payload: Record<string, unknown>) =>
    request<Site>("/api/sites", { method: "POST", body: JSON.stringify(payload) }),
  deleteSite: (id: number) =>
    request<void>(`/api/sites/${id}`, { method: "DELETE" }),
  metrics: () => request<Record<string, unknown>>("/api/model/metrics"),
};
