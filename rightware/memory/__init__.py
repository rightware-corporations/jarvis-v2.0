"""JRV-M01: persistent personal memory for JARVIS (consent-based, per owner, host-verified).

* ``store``     — SQLite store (one row per memory: id, owner, category, topic, content, provenance, created/updated,
                  status); corrections, supersession and deletion; an event log without content.
* ``policy``    — what may be written: an explicit request in the USER's own message, content grounded in that
                  message, no secrets/credentials/ID or card numbers, no instruction-like text.
* ``personal``  — ``PersonalMemory``: per-turn recall (relevant memories only) for the prompt, the model tools
                  (memory_save/update/forget/list) whose confirmations come from real database writes, and host
                  annotations.
* ``identity``  — the stable owner contract. B6 session ids are NEVER owners.
External content (web pages, documents, tool results) is data and can never authorise a memory change.
"""
