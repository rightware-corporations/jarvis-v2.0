# WP-01 — E0/E1 Release Scope and Target-Device Specification

**RIGHTWARE JARVIS** · **Report:** WP-01/R01  
**Date:** 2026-11-14 (Africa/Maputo)  
**Authorization:** [JRV-DEC-2026-11-14-001](DECISION_2026-11-14_BLUEPRINT_V1_APPROVAL.md), explicit operator approval  
**State:** READ-ONLY SPECIFICATION DELIVERED; device/user acceptance criteria still OPEN  
**Reference HEAD for source observations:** \`791f409a2de5268ab074044dc42b2b438c99e6a8\` at start of approval.  
**Source basis:** JRV-001–008, \`README.md\`, \`configs/local.toml\`, \`rightware/runtime.py\` and code-bound JRV-005; no live machine information invented.  
**Not authorized:** product source implementation, A4, Qwen inference, physical Windows testing, new dependencies, commercial release.

## 1. Outcome

The operator has **approved the Blueprint v1.0 as the RIGHTWARE architectural reference** and **E0/E1 as the first planning release envelopes**. This does **not** mean the following feature list is already implemented, or that the exact first-release UX/device targets are approved.

**E0 = internal integrated text alpha; E1 = Issa Windows personal pilot.** No E2/E3 release is approved.

## 2. Proposed E0 capability manifest — decision-ready

| Domain | Candidate mandatory UC | Acceptance outcome | Explicit exclusion |
|---|---|---|---|
| Text conversation | UC-001 | Answer grounded ordinary questions without unnecessary tools | Persistent user memory |
| Context and clarification | UC-002–005,013 | Referents, correction, ambiguity and missing fields on fixed Portuguese corpus | Unsupported live web claims |
| Planning and action routing | UC-012,022 | Distinguish planned task from actually executed task; bounded trusted synthetic tasks | Unrestricted task executor |
| Evidence and completion | UC-023/024 | Display verified, missing, incomplete, unknown/identity and halted states based on actual receipts | Claim original-document authenticity without trust |
| Cancel/deny/injection | UC-026–028 | Disallow unauthorized actions, stop new grants, ignore untrusted page instructions | Post-cancel irreversible rollback promise |
| Diagnostics | UC-030 | Display actual model/runtime capability and errors; no fabricated inference | Production installer |
| Status UX (limited) | UC-033 | Show task status/limitations in one usable text surface | Durable task history |
| Research negative fixtures only | UC-021 | Prove information pages/unknown originals do not imply success | Real publisher identity, COMPLETE_VERIFIED |

**Default permissions:** informational only. Optional bounded tools must be enabled explicitly and still pass RIGHTWARE \`AgentPolicy\`. Existing A1/A2/A3 default-OFF behaviour must remain regression-checked.

### E0 tests to specify before coding

- T-CTX: versioned Portuguese dialogue corpus with Earth/news ambiguity, corrections, pronouns and insufficient-context cases.
- T-CTRL: user text enters a single controller contract, not competing inconsistent \`chat\`/\`agent\` truth paths.
- T-POL: every enabled effect has an exact authorized decision; no-effect denial.
- T-EVD: malformed, unexecuted, timeout-late, duplicate and orphan calls never become verified success.
- T-QWEN: real model in a safe test fixture; record model name/version/context/hardware, and human judgment.
- T-UX: without inspecting logs, an internal tester can distinguish answer, plan, denial, partial and unknown.
- T-REG: all applicable A1/A2/A3 and issue #9 regression tests pass in pinned venv with no skipped required tests.

**Numerical quality/latency targets:** OPEN pending real baseline and sample size. A negative deterministic fixture has a strict no-unsafe-effect oracle; this does not prove zero deployment risk.

## 3. Proposed E1 personal Windows pilot capability manifest

**E1 inherits accepted E0** and adds only:

| Domain | Candidate mandatory UC | Observable outcome |
|---|---|---|
| Scoped durable memory | UC-008–011 | Explicit consent, durable preference write, read after restart, correction/delete and cache invalidation |
| Real Windows safe action | UC-020 initially | At least one selected action with explicit confirmation and observed OS postcondition; deny case tested |
| Voice I/O in Portuguese | UC-029 | Microphone STT, text fallback, TTS and cancellation on actual supported hardware |
| User interface and consent | UC-033 | Operator can see approved actions, capabilities and memories, without editing code |
| Repeatable setup and recovery | UC-030 | Clean target-device setup, environment diagnosis, model-unavailable handling and documented rollback |

**Wake word:** still a high-value original product expectation, but specifically OPEN whether it is mandatory for E1 gate versus an immediately following increment. Do **not** silently declare the final JARVIS experience complete while wake-word behaviour is absent.

**E1 exclusions without new decision:** arbitrary shell, broad filesystem writes, unauthenticated LAN server, email sending, calendar modifications, fully autonomous recurring jobs, multiuser access, unattended destructive actions, claimed commercial readiness.

### E1 acceptance evidence

- A recorded machine fingerprint (without serial numbers/secrets), Windows version/build, CPU, RAM, GPU/VRAM, microphone and audio output.
- Real install and executable model path, offline/no-cloud assurance verified as configured.
- Speech capture and playback in Portuguese with labeled error/latency measurements.
- Real action once allowed, and same call prevented when denied.
- Memory survives a process restart only after durable persistence, with deletion tested.
- User-visible status and consent; pilot feedback with documented defects and reproducible cases.
- Source SHA, exact runtime/model build and negative test fixtures attached to handoff.

## 4. Target hardware and environmental inventory — still unknown

The conversation and repository do **not** provide verified specifications of Issa's actual production computer. Kaggle Tesla T4 and remote GPU results cannot fill this field.

| Field | State | Why it matters |
|---|---|---|
| Windows version/build and architecture | UNKNOWN | TTS, process adapters, packaging and permissions |
| CPU/RAM available | UNKNOWN | Qwen/STT context and latency |
| GPU/VRAM and drivers | UNKNOWN | Local inference feasibility and fallback |
| Storage free space | UNKNOWN | Model weights, assets, cached STT and persistent records |
| Microphone/speaker and audio language voices | UNKNOWN | Real voice journey |
| Connectivity and desired offline constraints | OPEN | No obligatory cloud APIs, setup downloads and sync |
| User rights / organization device policy | UNKNOWN | Whether actions and autostart are permissible |
| Required task set for Issa | OPEN | Which action beyond Notepad/Calculator has real value |
| Privacy/retention preference | OPEN | Local memory consent, deletion/backup and logs |

**Next specification input:** a non-invasive system inventory and the operator's explicit decisions. No physical diagnostic command has been run and no machine requirements are invented.

## 5. Decision ledger for WP-01

| Decision | Proposal | Current status |
|---|---|---|
| WP01-D01 | E0 first, E1 second | APPROVED AS PLANNING ORDER via official decision |
| WP01-D02 | E0 UC manifest above as concrete acceptance obligations | PROPOSED; operator may revise |
| WP01-D03 | E1 subset above | PROPOSED; operator may revise |
| WP01-D04 | Require E1 voice wake word from first pilot | OPEN |
| WP01-D05 | Target device and minimum measurable hardware | OPEN |
| WP01-D06 | First 1–2 useful Windows operations | OPEN |
| WP01-D07 | Memory consent, retention and deletion | OPEN |
| WP01-D08 | Local native GUI vs secure local web UI | OPEN |
| WP01-D09 | Model quality/latency/pass thresholds | OPEN |
| WP01-D10 | Product code implementation authorization | NOT AUTHORIZED |

## 6. Boundary with WP-02 and the next implementation

WP-01 specifies *what* E0/E1 should promise and test. WP-02 determines whether current OpenJarvis code and RIGHTWARE assets can implement those commitments without duplication or weakening policy. Neither report grants implementation rights. After operator review, the first bounded implementation should target **one coherent local text interface + controller**, not an entire framework migration.

## 7. WP-01 acceptance and checkpoint

**Delivered:** candidate E0/E1 capability manifests, UC references, explicit exclusions, test classes, device specification worksheet, open decisions and real-acceptance evidence requirements.  
**Not delivered (and not falsely claimed):** actual Issa hardware numbers, consent policy approval, measured model/voice performance or a shipped E0/E1 build.

**Status:** WP-01 R01 documentation **COMPLETE WITH OPEN DECISIONS**, not official final release scope.

**Next:** operator review of WP01-D02–D09 and a separate authorization for any diagnostic/user-device test or implementation.
