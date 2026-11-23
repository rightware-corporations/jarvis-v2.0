// RIGHTWARE JARVIS i18n: PT-MZ by default, English supported. Used by the HUD components and, through the global
// __rwT, by the declared string patches of pinned upstream modules.
import { useSyncExternalStore } from 'react';
import { ptMZ } from './pt-MZ';
import { en } from './en';

export type Lang = 'pt-MZ' | 'en';
const DICTS: Record<Lang, Record<string, string>> = { 'pt-MZ': ptMZ, en };
const KEY = 'rw-lang';
const listeners = new Set<() => void>();

function stored(): Lang {
  try {
    const v = localStorage.getItem(KEY);
    return v === 'en' ? 'en' : 'pt-MZ';
  } catch {
    return 'pt-MZ';
  }
}

let current: Lang = typeof localStorage === 'undefined' ? 'pt-MZ' : stored();

export function getLang(): Lang {
  return current;
}

export function setLang(lang: Lang): void {
  current = lang;
  try {
    localStorage.setItem(KEY, lang);
  } catch {
    /* private mode: language only for this page */
  }
  if (typeof document !== 'undefined') document.documentElement.lang = lang === 'en' ? 'en' : 'pt-MZ';
  listeners.forEach((l) => l());
}

export function t(key: string, vars?: Record<string, string | number>): string {
  let s = DICTS[current][key] ?? DICTS['pt-MZ'][key] ?? key;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v));
  return s;
}

export function useLang(): Lang {
  return useSyncExternalStore((cb) => {
    listeners.add(cb);
    return () => listeners.delete(cb);
  }, getLang, getLang);
}

export function installGlobalTranslator(): void {
  globalThis.__rwT = (key: string) => t(key);
  if (typeof document !== 'undefined') document.documentElement.lang = current === 'en' ? 'en' : 'pt-MZ';
}
