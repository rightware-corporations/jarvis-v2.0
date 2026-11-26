// RIGHTWARE JARVIS (INT01): documents and personal-memory screen. Same origin, session cookie sent by the browser;
// the owner is decided by the server from the authenticated session (never sent from here).
export interface DocItem { id: string; name: string; kind: string; units: number; created_at: number }
export interface MemItem { id: string; category: string; topic: string; content: string; updated_at: number }
export interface UploadResult { status: string; document_id?: string; name?: string; reason?: string;
                               units?: number; injection_suspected?: boolean }

export const MAX_UPLOAD = 5 * 1024 * 1024;
export const ACCEPT = '.pdf,.txt,.csv,application/pdf,text/plain,text/csv';

/** Client-side pre-check only (the server re-validates the real format and limits). */
export function precheck(name: string, size: number): string | null {
  if (!/\.(pdf|txt|csv)$/i.test(name)) return 'format';
  if (size <= 0) return 'empty';
  if (size > MAX_UPLOAD) return 'size';
  return null;
}

async function json<T>(r: Response): Promise<T> {
  const body = await r.json().catch(() => ({}));
  if (r.status === 401) throw Object.assign(new Error('session'), { status: 401 });
  if (!r.ok && !(body && typeof body === 'object' && 'status' in body)) throw Object.assign(new Error(String(r.status)), { status: r.status });
  return body as T;
}

export async function documentsAvailable(): Promise<boolean> {
  try { const r = await fetch('/v1/rightware/documents', { credentials: 'same-origin' }); return r.ok; }
  catch { return false; }
}

export async function listDocuments(): Promise<DocItem[]> {
  const r = await fetch('/v1/rightware/documents', { credentials: 'same-origin' });
  return (await json<{ documents: DocItem[] }>(r)).documents ?? [];
}

export async function uploadDocument(file: File): Promise<UploadResult> {
  const r = await fetch('/v1/rightware/documents/upload', {
    method: 'POST', credentials: 'same-origin', body: file,
    headers: { 'Content-Type': 'application/octet-stream', 'X-Rightware-Filename': encodeURIComponent(file.name) },
  });
  return json<UploadResult>(r);
}

export async function deleteDocument(id: string): Promise<boolean> {
  const r = await fetch('/v1/rightware/documents/delete', { method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ document_id: id }) });
  return r.ok;
}

export async function listMemories(): Promise<MemItem[] | null> {
  const r = await fetch('/v1/rightware/memory', { credentials: 'same-origin' });
  if (r.status === 403) return null;                       // memory not enabled / session without identity
  return (await json<{ memories: MemItem[] }>(r)).memories ?? [];
}

export async function correctMemory(id: string, text: string): Promise<{ status: string; reason?: string }> {
  const r = await fetch('/v1/rightware/memory/correct', { method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ memory_id: id, text }) });
  return json(r);
}

export async function deleteMemory(id: string): Promise<boolean> {
  const r = await fetch('/v1/rightware/memory/delete', { method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ memory_id: id }) });
  return r.ok;
}

export const LIBRARY_CHANGED = 'rw-library-changed';
