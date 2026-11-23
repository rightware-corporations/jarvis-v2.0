// Typed client of the RIGHTWARE HUD API (same origin; the local session cookie is sent by the browser).
export type CapabilityStatus = 'INTEGRADA' | 'PARCIAL' | 'NAO_INTEGRADA' | 'BLOQUEADA';
export interface Capability { id: string; label: string; status: CapabilityStatus; reason: string; mission?: boolean; description?: string }
export interface Receipt { seq: number; tool: string; status: string }
export interface Objective { id: string; status: string; receipt: number | null }
export interface Outcome {
  state: string; label: string; verified: boolean; capability?: string; operational_state?: string;
  receipts?: Receipt[]; objectives?: Objective[]; changes?: string[]; commentary_unverified?: string;
  seconds?: number; error_code?: string; halt?: string; refusal?: string;
}
export interface HudState {
  engine: { healthy: boolean; models: string[]; default_model: string };
  model_busy: number;
  capabilities: Capability[];
  pending: { capability: string; expires_in: number } | null;
  task: { running: boolean; capability: string | null; elapsed: number | null };
  last: Outcome | null;
}
export class SessionError extends Error {}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { credentials: 'same-origin', ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) } });
  if (r.status === 401) throw new SessionError('session');
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(body.error ?? String(r.status)), { body });
  return body as T;
}

export const fetchState = () => call<HudState>('/v1/rightware/state');
export const requestMission = (capability: string) =>
  call<{ state: string; label: string; code?: string; description?: string; expires_in?: number }>(
    '/v1/rightware/tasks/request', { method: 'POST', body: JSON.stringify({ capability }) });
export const authorizeMission = (code: string) =>
  call<{ state: string; text: string; hud: HudState }>('/v1/rightware/tasks/authorize',
    { method: 'POST', body: JSON.stringify({ code }) });
export const cancelMission = () => call<{ state: string }>('/v1/rightware/tasks/cancel', { method: 'POST', body: '{}' });

/** Only a typed 6-hex code can be submitted (no click-only approval). */
export const isOperatorCode = (s: string) => /^[0-9A-Fa-f]{6}$/.test(s.trim());
