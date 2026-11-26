// INT01: client-side pre-check of uploads (the server re-validates the real format and limits) and static rendering
// of the library panel (initial state; data comes from the server, the owner is decided by the server).
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ACCEPT, MAX_UPLOAD, precheck } from '../lib/knowledge-api';
import { LibraryPanel } from './LibraryPanel';
import { setLang } from '../i18n';

describe('upload pre-check', () => {
  it('accepts only pdf/txt/csv within 5 MB', () => {
    expect(precheck('relatorio.pdf', 10)).toBeNull();
    expect(precheck('dados.CSV', 10)).toBeNull();
    expect(precheck('x.docx', 10)).toBe('format');
    expect(precheck('x.txt', 0)).toBe('empty');
    expect(precheck('x.pdf', MAX_UPLOAD + 1)).toBe('size');
    expect(ACCEPT).toContain('.pdf');
  });
});

describe('LibraryPanel', () => {
  it('renders the documents and memory sections with the separation note', () => {
    setLang('pt-MZ');
    const html = renderToStaticMarkup(<LibraryPanel onClose={() => {}} />);
    expect(html).toContain('Documentos e memória');
    expect(html).toContain('data-rw="docs-empty"');
    expect(html).toContain('Os documentos nunca criam memórias');
  });
});
