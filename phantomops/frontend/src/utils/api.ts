// PhantomOps™ — API Client

const BASE = '/api';

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('phantomops_token');
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  // Auth
  login: (body: { drone_id: string; secret: string }) =>
    request<{ access_token: string }>('/auth/login', { method: 'POST', body: JSON.stringify(body) }),

  // Fleet
  getFleetSummary: () => request<Record<string, unknown>>('/fleet/summary'),
  getDrones: () => request<unknown[]>('/fleet/drones'),
  getDrone: (id: string) => request<unknown>(`/fleet/drones/${id}`),
  getDroneHealth: (id: string) => request<unknown>(`/fleet/drones/${id}/health`),

  // Telemetry
  getLatestTelemetry: (id: string) => request<unknown>(`/telemetry/${id}/latest`),
  getTelemetryHistory: (id: string, limit = 200, since?: number) =>
    request<unknown[]>(`/telemetry/${id}/history?limit=${limit}${since ? `&since=${since}` : ''}`),
  getConfidence: (id: string) => request<unknown>(`/telemetry/${id}/confidence`),

  // Missions
  createMission: (body: unknown) =>
    request<{ id: string }>('/missions/', { method: 'POST', body: JSON.stringify(body) }),
  getMission: (id: string) => request<unknown>(`/missions/${id}`),
  activateMission: (id: string) =>
    request<unknown>(`/missions/${id}/activate`, { method: 'PUT' }),
  abortMission: (id: string) =>
    request<unknown>(`/missions/${id}/abort`, { method: 'PUT' }),
  getActiveMission: (droneId: string) =>
    request<unknown>(`/missions/drone/${droneId}/active`),
  sendCommand: (droneId: string, body: unknown) =>
    request<unknown>(`/missions/${droneId}/command`, { method: 'POST', body: JSON.stringify(body) }),

  // Analytics
  getDriftSummary: (id: string, windowS = 3600) =>
    request<unknown>(`/analytics/${id}/drift?window_s=${windowS}`),
  getConfidenceTrend: (id: string, windowS = 3600, bucketS = 60) =>
    request<unknown>(`/analytics/${id}/confidence-trend?window_s=${windowS}&bucket_s=${bucketS}`),
  getGnssEvents: (id: string) => request<unknown>(`/alerts/${id}`),
  getFleetAnalytics: () => request<unknown>('/analytics/fleet/summary'),
};
