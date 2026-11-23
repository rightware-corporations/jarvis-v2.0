import type { ResearchEvent, SSEEvent } from '@/types';
import { getBase, authHeaders } from '@/lib/api';
import { useAppStore } from '@/lib/store';

// RIGHTWARE JARVIS (UI-02): pinned upstream SSE client; the chat request also carries the explicit conversation id
// (X-Rightware-Conversation) so the host binds the dialogue to its own session (R-5). Generated from the pinned file.
const conversationHeader = (): Record<string, string> => {
  const id = useAppStore.getState().activeId;
  return id && /^[A-Za-z0-9_-]{8,64}$/.test(id) ? { 'X-Rightware-Conversation': id } : {};
};

export interface ChatRequest {
  model: string;
  messages: Array<{ role: string; content: string }>;
  stream: true;
  temperature?: number;
  max_tokens?: number;
}

export async function* streamChat(
  request: ChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const base = getBase();
  const response = await fetch(`${base}/v1/chat/completions`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json', ...conversationHeader() }),
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    throw new Error(`Chat request failed: ${response.status}`);
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      let currentEvent: string | undefined;

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') return;
          yield { event: currentEvent, data };
          currentEvent = undefined;
        } else if (line.trim() === '') {
          currentEvent = undefined;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export async function* streamResearch(
  query: string,
  model?: string,
  signal?: AbortSignal,
): AsyncGenerator<ResearchEvent> {
  // /api/research is mounted at the server root — strip any trailing /v1
  // from the base so configurations like "http://host:8000/v1" still resolve.
  const base = getBase().replace(/\/v1\/?$/, '');
  const response = await fetch(`${base}/api/research`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ query, ...(model ? { model } : {}) }),
    signal,
  });

  if (!response.ok) {
    throw new Error(`Research request failed: ${response.status}`);
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6);
        if (data === '[DONE]') return;
        try {
          const parsed = JSON.parse(data) as ResearchEvent;
          yield parsed;
          if (parsed.type === 'done') return;
        } catch {
          // skip malformed chunks
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
