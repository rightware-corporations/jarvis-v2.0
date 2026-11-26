# JRV-LIVE02 — Cloud runtime recovery (implementation, not deployment)

**Scope:** existing cloud host only. No operator PC installation. No new tunnel, external storage provider, paid service, upload of personal data or unattended restart. Claude can execute the following on return.

## 1. Recover the correct code and runtime
- Confirm the existing integration branch and `git status --short`. If clean, fetch and fast-forward only. Never reset or overwrite a local change.
- Check Ollama listening only on 127.0.0.1:11434 and the expected Qwen model; if missing, rebuild only after the operator approves any downloads.
- With prepared runtime: `python -m rightware.gui frontend-check`, then `python -m rightware.gui frontend-build`. Do not run the full GUI setup if only a frontend rebuild is needed (it can recreate the venv).
- Run LIVE02 unit tests, then the INT01/R02 synthetic E2E. Physical acceptance remains a separate gate.

## 2. State recovery contract
The host must provision an **actually persistent**, private, access-controlled volume outside the checkout. A directory inside an ephemeral container, even with correct permissions, is not a durable volume. Confirm provider retention, encryption and access separately; no provider has been selected here.

The LIVE02 state directory contains exactly the named stores used by the launcher: `mem.sqlite3` and `docs.sqlite3`. Use the existing authorised databases; do not silently create new ones if the originals are missing. Migration from prior live paths requires operator approval, quiescence of the old service and a SQLite-aware transfer (including committed WAL transactions), not a raw copy of active DB files. No automatic backup or restore is implemented: retention/deletion policies and external destination are undecided.

Only for an explicitly approved **new** installation, not recovery:
```bash
.runtime/gui/venv/bin/python -m rightware.gui.recovery init --state-dir /path/to/private-persistent-volume/jarvis
```
Parent must already exist; init refuses an existing directory. A partial init requires review.

Preflight (metadata only):
```bash
.runtime/gui/venv/bin/python -m rightware.gui.recovery check --state-dir /path/to/private-persistent-volume/jarvis --voice
```
Exit 0 = required files, permissions, SQLite quick_check, expected schema, disk reserve, prepared GUI, overlay match, loopback config, model tag and voice asset presence. NOT proof of inference, physical speech, database identity, mount durability or tunnel reachability.

## 3. Recovery of an authorised private window
Use existing B6 procedure and confirm the original UTC expiry and active operator permission. Do not recreate a terminated/expired window; request a new authorization. Example placeholders (not commands to run verbatim):
```bash
.runtime/gui/venv/bin/python -m labs.presentation.serve --offline --voz \
  --donos operador=lab:operador-live --documentos \
  --state-dir /path/to/private-persistent-volume/jarvis \
  --public-origin "$APPROVED_ORIGIN" --public-minutes 59 --public-deadline "$ORIGINAL_EXPIRY_EPOCH"
```
No automatic tunnel creation. Use the same owner mapping as the existing data; do not change owner IDs casually. The original private access cap is enforced independently of the process restart; fresh links are minted by the existing authentication subsystem. No Issa link unless explicitly authorised. The example is offline intentionally. Network/proxy mode remains subject to its own original authorization, request limits and persistent budget evidence; do not restart with a reset network budget.

## 4. Operational recovery and acceptance
- If all host processes stop together, diagnose host lifetime separately from STT.
- On restart, confirm checkout, existing databases and original deadline; do not renew access automatically.
- Use authenticated browser health and real STT, then TTS, memory/document recall, and isolation. Stop unused relay and revoke sessions at window expiry.
- If durable storage is absent, report BLOCKED for personal data; only a synthetic lab preview is acceptable. No claim of 24/7 uptime on a disposable container.

**Status:** code and tests authored; actual cloud volume, GUI runtime, inference, E2E and restart recovery not verified in this session.
