"""JRV-K01: document knowledge for JARVIS — upload, validation, extraction, segmentation with provenance, private
per-owner SQLite/FTS5 index, relevant retrieval into the SAME conversational core, deletion.

* ``ingest``   — real-format validation (PDF/TXT/CSV), safe naming, SHA-256, extraction (PDF pages via the R02
                 ``pdftotext`` wrapper; TXT lines; CSV rows), segments with locators (página N / linhas a–b).
* ``store``    — SQLite + FTS5 (BM25 ranking) under ``.runtime/knowledge`` (never committed); owner isolation;
                 deletion of the document AND its index.
* ``library``  — ``DocumentLibrary``: per-turn retrieval (bounded passages, never whole large documents), the model
                 tools (doc_list/doc_search/doc_read/doc_delete), citation validation against the passages actually
                 provided (R02 validator), host source lines.
Documents are DATA: they can never authorise operations or memory changes. Owners follow the M01 identity contract.
"""
