// HUD state: polled from the backend (never invented). Also owns the CPU budget signals:
//  - html.rw-busy while the model or a mission is working → all decorative animation is paused (R-7),
//  - html.rw-offline when the local engine is unavailable.
import { useSyncExternalStore } from 'react';
import { create } from 'zustand';
import { fetchState, SessionError, type HudState } from './rightware-api';

export type CoreMode = 'offline' | 'ready' | 'thinking' | 'mission' | 'verified' | 'unverified' | 'failed';

interface HudStore {
  state: HudState | null;
  error: 'session' | 'network' | null;
  chatStreaming: boolean;
  setChatStreaming: (v: boolean) => void;
  refresh: () => Promise<void>;
}

export const useHud = create<HudStore>((set, get) => ({
  state: null,
  error: null,
  chatStreaming: false,
  setChatStreaming: (v) => { set({ chatStreaming: v }); applyBudget(get()); },
  refresh: async () => {
    try {
      const state = await fetchState();
      set({ state, error: null });
    } catch (e) {
      set({ error: e instanceof SessionError ? 'session' : 'network' });
    }
    applyBudget(get());
  },
}));

export function isBusy(s: Pick<HudStore, 'state' | 'chatStreaming'>): boolean {
  return !!(s.chatStreaming || s.state?.task.running || (s.state?.model_busy ?? 0) > 0);
}

export function coreMode(s: Pick<HudStore, 'state' | 'chatStreaming' | 'error'>): CoreMode {
  const st = s.state;
  if (!st || s.error || !st.engine.healthy) return 'offline';
  if (st.task.running) return 'mission';
  if (s.chatStreaming || st.model_busy > 0) return 'thinking';
  if (st.last) {
    if (st.last.verified) return 'verified';
    if (st.last.state === 'EXECUCAO_FALHADA' || st.last.state === 'TAREFA_NAO_AUTORIZADA') return 'failed';
    return 'unverified';
  }
  return 'ready';
}

function applyBudget(s: HudStore): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  root.classList.toggle('rw-busy', isBusy(s));
  root.classList.toggle('rw-offline', coreMode(s) === 'offline');
}

let timer: ReturnType<typeof setTimeout> | null = null;
/** One poller for the whole app: 1.5 s while visible and working, 5 s idle, 15 s when the tab is hidden. */
export function startHudPolling(): void {
  if (timer || typeof window === 'undefined') return;
  const tick = async () => {
    await useHud.getState().refresh();
    const hidden = document.visibilityState === 'hidden';
    const busy = isBusy(useHud.getState());
    timer = setTimeout(tick, hidden ? 15000 : busy ? 1500 : 5000);
  };
  void tick();
}

/** Live HUD value with the SAME snapshot on client and server render (zustand's server snapshot is the initial
 * state). Selectors must return stable values (the state object, primitives). */
export function useHudValue<T>(select: (s: HudStore) => T): T {
  const get = () => select(useHud.getState());
  return useSyncExternalStore(useHud.subscribe, get, get);
}
