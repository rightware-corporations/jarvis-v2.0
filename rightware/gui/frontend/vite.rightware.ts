// RIGHTWARE JARVIS HUD — build/test config layered on the PINNED OpenJarvis frontend (UI-02).
// The frontend copy comes from `git archive` of the vendor pin; this folder is copied next to it as `rightware/`.
// Nothing in the vendor is edited: listed upstream modules are swapped at module-resolution time, and listed
// upstream strings are routed through the RIGHTWARE translator at transform time — both verified against the
// sha256 of the pinned file (any drift fails the build).
import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import { defineConfig, mergeConfig, type Plugin, type PluginOption, type UserConfig } from 'vite';
import upstream from '../vite.config';
import manifest from './overlay.manifest.json';

const HERE = import.meta.dirname;
const FRONTEND = path.resolve(HERE, '..');
const sha256 = (file: string) => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');

function checkPinned(rel: string, expected: string) {
  const abs = path.resolve(FRONTEND, rel);
  const got = sha256(abs);
  if (got !== expected) throw new Error(`RIGHTWARE overlay drift: ${rel} sha256 ${got} != pinned ${expected}`);
  return abs;
}

export function rightwareOverlay(): Plugin {
  const swap = new Map<string, string>();
  for (const r of manifest.replacements) swap.set(checkPinned(r.upstream, r.sha256), path.resolve(HERE, r.replacement));
  const strings = new Map<string, { find: string; replace: string; count: number }[]>();
  for (const s of manifest.strings) strings.set(checkPinned(s.file, s.sha256), s.items);
  checkPinned(manifest.html.file, manifest.html.sha256);
  return {
    name: 'rightware-overlay',
    enforce: 'pre',
    async resolveId(source, importer, options) {
      const resolved = await this.resolve(source, importer, { ...options, skipSelf: true });
      const id = resolved?.id.split('?')[0];
      return id && swap.has(id) ? swap.get(id)! : null;
    },
    transformIndexHtml(html) {
      let out = html;
      for (const it of manifest.html.items) {
        const n = out.split(it.find).length - 1;
        if (n !== it.count) throw new Error(`RIGHTWARE html patch: "${it.find}" found ${n}x, expected ${it.count}`);
        out = out.split(it.find).join(it.replace);
      }
      return out;
    },
    transform(code, id) {
      const items = strings.get(id.split('?')[0]);
      if (!items) return null;
      let out = code;
      for (const it of items) {
        const n = out.split(it.find).length - 1;
        if (n !== it.count) throw new Error(`RIGHTWARE i18n patch: "${it.find}" found ${n}x in ${id}, expected ${it.count}`);
        out = out.split(it.find).join(it.replace);
      }
      return { code: out, map: null };
    },
  };
}

// The original PWA/service worker is dropped (stale-cache risk R-12); everything else of the pinned config is kept.
const isPwa = (p: PluginOption): boolean => !!p && typeof p === 'object' && 'name' in p && String(p.name).startsWith('vite-plugin-pwa');
const base = upstream as UserConfig;
const basePlugins = ((base.plugins ?? []) as PluginOption[]).flat(3).filter((p) => !isPwa(p));

export default mergeConfig({ ...base, plugins: basePlugins }, defineConfig({
  plugins: [rightwareOverlay()],
  resolve: { alias: { '@rw': path.resolve(HERE, 'src') } },
  build: { emptyOutDir: true },
  // vitest reads this block
  test: {
    include: ['rightware/src/**/*.test.{ts,tsx}', 'src/**/*.test.{ts,tsx}'],
    exclude: manifest.replacedTests,
  },
}));
