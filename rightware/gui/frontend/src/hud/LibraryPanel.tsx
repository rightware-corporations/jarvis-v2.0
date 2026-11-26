// RIGHTWARE JARVIS (INT01): "Anexar documento" next to the microphone + a minimal "Documentos e memória" panel
// (list/delete documents; list/correct/delete personal memories). Shown only when the host enabled the capability
// (the routes answer); no redesign of the interface.
import { useEffect, useRef, useState } from 'react';
import { BookOpen, Paperclip, Trash2, Pencil, X } from 'lucide-react';
import { t, useLang } from '../i18n';
import {
  ACCEPT, LIBRARY_CHANGED, correctMemory, deleteDocument, deleteMemory, documentsAvailable, listDocuments,
  listMemories, precheck, uploadDocument, type DocItem, type MemItem,
} from '../lib/knowledge-api';

function changed() { window.dispatchEvent(new Event(LIBRARY_CHANGED)); }

export function AttachButton() {
  useLang();
  const [on, setOn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { void documentsAvailable().then(setOn); }, []);
  if (!on) return null;
  const pick = async (f: File | undefined) => {
    if (!f) return;
    const bad = precheck(f.name, f.size);
    if (bad) { setMsg(t(`docs.err.${bad}`)); return; }
    setBusy(true); setMsg(t('docs.uploading'));
    try {
      const r = await uploadDocument(f);
      if (r.status === 'OK' || r.status === 'DUPLICATE') {
        setMsg(t(r.status === 'OK' ? 'docs.ok' : 'docs.dup').replace('{name}', r.name ?? f.name)
               + (r.injection_suspected ? ' ' + t('docs.injection') : ''));
        changed();
      } else setMsg(t('docs.refused').replace('{reason}', r.reason ?? ''));
    } catch { setMsg(t('docs.failed')); }
    finally { setBusy(false); if (input.current) input.current.value = ''; }
  };
  return (
    <span className="flex items-center gap-1">
      <input ref={input} type="file" accept={ACCEPT} hidden data-rw="doc-input"
             onChange={(e) => void pick(e.target.files?.[0])} />
      <button type="button" disabled={busy} title={t('docs.attach')} aria-label={t('docs.attach')} data-rw="doc-attach"
              className="p-2 rounded-xl shrink-0" style={{ color: 'var(--color-text-secondary)', opacity: busy ? 0.4 : 1 }}
              onClick={() => input.current?.click()}>
        <Paperclip size={16} />
      </button>
      <LibraryButton />
      {msg && <span role="status" data-rw="doc-status" className="text-xs" style={{ color: 'var(--color-text-secondary)', maxWidth: 260 }}>{msg}</span>}
    </span>
  );
}

function LibraryButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" title={t('library.title')} aria-label={t('library.title')} data-rw="library-open"
              className="p-2 rounded-xl shrink-0" style={{ color: 'var(--color-text-secondary)' }} onClick={() => setOpen(true)}>
        <BookOpen size={16} />
      </button>
      {open && <LibraryPanel onClose={() => setOpen(false)} />}
    </>
  );
}

export function LibraryPanel({ onClose }: { onClose: () => void }) {
  useLang();
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [mems, setMems] = useState<MemItem[] | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const load = async () => {
    try { setDocs(await listDocuments()); } catch { setDocs([]); }
    try { setMems(await listMemories()); } catch { setMems(null); }
  };
  useEffect(() => {
    void load();
    const h = () => void load();
    window.addEventListener(LIBRARY_CHANGED, h);
    return () => window.removeEventListener(LIBRARY_CHANGED, h);
  }, []);
  const delDoc = async (d: DocItem) => {
    if (!window.confirm(t('docs.confirmDelete').replace('{name}', d.name))) return;
    setNote(await deleteDocument(d.id) ? t('docs.deleted') : t('docs.failed')); void load();
  };
  const fixMem = async (m: MemItem) => {
    const text = window.prompt(t('mem.correctPrompt'), m.content);
    if (text === null || !text.trim()) return;
    const r = await correctMemory(m.id, text);
    setNote(r.status === 'OK' ? t('mem.corrected') : t('mem.refused').replace('{reason}', r.reason ?? ''));
    void load();
  };
  const delMem = async (m: MemItem) => {
    if (!window.confirm(t('mem.confirmDelete'))) return;
    setNote(await deleteMemory(m.id) ? t('mem.deleted') : t('docs.failed')); void load();
  };
  return (
    <div role="dialog" aria-label={t('library.title')} data-rw="library-panel" className="rw-library"
         style={{ position: 'fixed', right: 16, bottom: 96, width: 'min(420px, calc(100vw - 32px))', maxHeight: '60vh',
                  overflow: 'auto', zIndex: 60, background: 'var(--color-bg-secondary, #0b1020)',
                  border: '1px solid var(--color-border, #223)', borderRadius: 12, padding: 12 }}>
      <div className="flex items-center justify-between mb-2">
        <strong>{t('library.title')}</strong>
        <button type="button" onClick={onClose} aria-label={t('library.close')} data-rw="library-close"><X size={16} /></button>
      </div>
      {note && <p role="status" className="text-xs mb-2">{note}</p>}
      <h4 className="text-sm mb-1">{t('docs.title')}</h4>
      {docs.length === 0 ? <p className="text-xs mb-2" data-rw="docs-empty">{t('docs.empty')}</p> : (
        <ul className="mb-3" data-rw="docs-list">
          {docs.map((d) => (
            <li key={d.id} className="flex items-center justify-between text-xs py-1" data-rw={`doc-${d.id}`}>
              <span>{d.name} · {d.kind.toUpperCase()} · {d.units} {d.kind === 'pdf' ? t('docs.pages') : t('docs.lines')}</span>
              <button type="button" onClick={() => void delDoc(d)} aria-label={t('docs.delete')} data-rw="doc-delete"><Trash2 size={14} /></button>
            </li>))}
        </ul>)}
      <h4 className="text-sm mb-1">{t('mem.title')}</h4>
      {mems === null ? <p className="text-xs" data-rw="mem-off">{t('mem.off')}</p> : mems.length === 0 ?
        <p className="text-xs" data-rw="mem-empty">{t('mem.empty')}</p> : (
        <ul data-rw="mem-list">
          {mems.map((m) => (
            <li key={m.id} className="flex items-center justify-between text-xs py-1 gap-2" data-rw={`mem-${m.id}`}>
              <span>«{m.content}» <em>({m.category})</em></span>
              <span className="flex gap-1">
                <button type="button" onClick={() => void fixMem(m)} aria-label={t('mem.correct')} data-rw="mem-correct"><Pencil size={14} /></button>
                <button type="button" onClick={() => void delMem(m)} aria-label={t('mem.delete')} data-rw="mem-delete"><Trash2 size={14} /></button>
              </span>
            </li>))}
        </ul>)}
      <p className="text-xs mt-2" style={{ opacity: 0.7 }}>{t('library.note')}</p>
    </div>
  );
}
