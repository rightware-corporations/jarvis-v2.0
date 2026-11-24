"""WEB-01 W3.1/W3.2: user-driven research (``pesquisa-livre``) on the SAME stack as W2/W3: EgressGuard + provider +
ResearchToolkit receipts + ControlPlane (single-use code bound to the exact question and plan) + HUD timeline.

W3.2 adaptive loop (bounded; every decision recorded):
  search (Gateway) → open the best new result (a second only if the first added nothing for the missing parts) →
  structured evidence candidates per answer part (``evidence``) → the local model ASSESSES coverage and proposes the
  next query → the HOST checks coverage against the evidence → continue / reformulate / stop.
  Early stop ONLY when the host confirms every answer part is covered; a model "sufficient" is not enough, and spare
  budget is not a reason to continue. Bounded by policy budgets, ≤ MAX_ITERATIONS, ≤ MAX_MODEL_CALLS, cancellation.
Then one SYNTHESIS call proposes claims; the host validates them strictly and COMPOSES the answer from accepted claims
only (``evidence.validate``). The model's free text is never shown as a conclusion. Result states: RESPOSTA_FUNDAMENTADA
(all parts grounded), EXECUCAO_PARCIAL, RESULTADO_DESCONHECIDO (abstention) or TAREFA_CANCELADA — never
RESULTADO_VERIFICADO (lexical grounding is not semantic verification)."""
from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from rightware.control_plane import State, TaskOutcome
from rightware.web01 import evidence as EV
from rightware.web01 import providers as PV
from rightware.web01.egress import EgressGuard, EgressPolicy, build_fetcher, guarantees
from rightware.web01.llm import ModelError, local_model
from rightware.web01.mission import MODE_LABEL, _Either
from rightware.web01.planner import FORBIDDEN_IN_QUERY, Plan, content_terms, make_plan
from rightware.web01.research import ResearchToolkit

CAPABILITY = "pesquisa-livre"
ROOT = Path(__file__).resolve().parents[2]
MAX_ITERATIONS = 4
MAX_MODEL_CALLS = 5            # assessments + 1 synthesis (planning happens before authorisation)
FINAL = {"GROUNDED": State.RESPOSTA_FUNDAMENTADA, "PARTIAL": State.EXECUCAO_PARCIAL,
         "ABSTAIN": State.RESULTADO_DESCONHECIDO}


def reformulate(query: str, question: str) -> str | None:
    """Host rule (deterministic): keep only the question's content terms, longest first; None if no change."""
    terms = sorted(dict.fromkeys(content_terms(question)), key=len, reverse=True)[:4]
    alt = " ".join(terms)
    return alt if alt and alt.lower() != query.lower() else None


def _valid_query(q) -> str | None:
    if not isinstance(q, str):
        return None
    q = " ".join(q.split())
    return q if 3 <= len(q) <= 100 and not FORBIDDEN_IN_QUERY.search(q) else None


class FreeResearchMission:
    capability = CAPABILITY
    accepts_params = True

    def __init__(self, policy: EgressPolicy | None = None, *, model: str = "qwen3.5:2b", model_call=None,
                 fetcher_factory=None, runtime: Path | None = None, clock=time.monotonic):
        self.policy = policy or EgressPolicy.load()
        public = self.policy.mode == "public"
        self.provider = PV.for_policy(self.policy)
        if fetcher_factory is None:                      # public: refused here unless the policy is W3-authorised
            build_fetcher(self.policy, allow_public=public)
            fetcher_factory = lambda stop: build_fetcher(self.policy, allow_public=public)  # noqa: E731
        self._fetcher_factory = fetcher_factory
        self.model = model
        self.call = model_call or local_model(model)
        self.runtime = runtime or ROOT / ".runtime" / "web01-missions"
        self.clock = clock
        self._cancel = threading.Event()
        self.description = (f"Pesquisa LIVRE de leitura — modo {MODE_LABEL[self.policy.mode]}. O JARVIS propõe um plano "
                            "(modelo local, validado pelo anfitrião); só executa depois do código do operador; investiga "
                            "de forma adaptativa e pára quando a evidência cobre a pergunta; a resposta é construída só a "
                            "partir de afirmações fundamentadas. Afirmações NÃO são verificadas semanticamente.")

    def plan(self, question: str) -> tuple[Plan, dict]:
        return make_plan(question, self.call, self.model)

    def cancel(self) -> bool:
        self._cancel.set()
        return True

    def _model(self, system, user, ledger):
        if ledger["calls"] >= MAX_MODEL_CALLS:
            raise ModelError("limite de chamadas ao modelo atingido")
        ledger["calls"] += 1
        raw, secs = self.call(system, user)
        ledger["seconds"] += secs
        return raw, secs

    def run(self, cancelled: threading.Event, on_start=None, *, params: dict | None = None) -> TaskOutcome:
        started = self.clock()
        self._cancel.clear()
        stop = _Either(cancelled, self._cancel)
        if not params or not isinstance(params.get("plan"), Plan):
            raise PermissionError("pesquisa livre sem plano autorizado")
        plan: Plan = params["plan"]
        parts = list(plan.answer_parts) or [plan.question]
        guard = EgressGuard(self.policy, self._fetcher_factory(stop), cancelled=stop, clock=self.clock)
        kit = ResearchToolkit(guard, self.provider)
        if on_start:
            on_start()
        queue, tried, opened, iterations = list(plan.queries), [], set(), []
        ledger = {"calls": 0, "seconds": 0.0}
        cands, covered, stop_reason = [], set(), "limite de iterações atingido"
        for it in range(1, MAX_ITERATIONS + 1):
            if stop.is_set():
                stop_reason = "cancelado pelo operador"
                break
            if self.policy.max_requests_per_mission - guard.requests < 2:
                stop_reason = "orçamento de pedidos insuficiente para outra pesquisa"
                break
            query = next((q for q in queue if q not in tried), None) or reformulate(tried[-1] if tried else "",
                                                                                     plan.question)
            if not query or query in tried:
                stop_reason = "sem consultas novas"
                break
            tried.append(query)
            t0 = self.clock()
            rs, results = kit.web_search_public(query)
            step = {"iteration": it, "query": query, "search_receipt": rs["seq"], "search_status": rs["status"],
                    "opened": []}
            missing_before = [i for i in range(len(parts)) if i not in covered]
            for k, url in enumerate([u for u in results if u not in opened][:2]):
                if stop.is_set() or self.policy.max_requests_per_mission - guard.requests < 1:
                    break
                if not self.policy.host_allowed(urlsplit(url).hostname or ""):
                    continue
                if k == 1:                         # open a 2nd result only if the 1st added nothing useful
                    probe = EV.candidates(plan.question, [parts[i] for i in missing_before],
                                          EV.documents(kit.receipts, kit.kept))
                    if any(max(c["scores"][1:] or [0]) >= 0.3 and c["seq"] == step["opened"][-1]["receipt"]
                           for c in probe):
                        step["second_result"] = "evitado: o primeiro resultado já trouxe evidência para o que falta"
                        break
                opened.add(url)
                ro, _ = kit.web_open_public(url)
                step["opened"].append({"receipt": ro["seq"], "url": url, "status": ro["status"]})
            step["network_s"] = round(self.clock() - t0, 2)
            cands = EV.candidates(plan.question, parts, EV.documents(kit.receipts, kit.kept))
            step["candidates"] = len(cands)
            proposal, raw = None, ""
            if cands and not stop.is_set():
                try:
                    raw, secs = self._model(EV.ASSESS_SYSTEM, EV.assess_prompt(plan.question, parts, tried, cands),
                                            ledger)
                    step["assess_s"] = secs
                    proposal = json.loads(raw)
                except (ModelError, ValueError) as exc:
                    step["assess_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
            covered, detail = EV.host_coverage(parts, cands, proposal)
            step["coverage"] = {"host_covered": sorted(covered), "detail": detail,
                                "model_sufficient": bool(proposal and proposal.get("sufficient")),
                                "model_reason": str((proposal or {}).get("reason", ""))[:200]}
            iterations.append(step)
            if len(covered) == len(parts):
                stop_reason = "cobertura completa confirmada pelo anfitrião (paragem antecipada)"
                step["decision"] = "parar"
                break
            missing = [parts[i] for i in range(len(parts)) if i not in covered]
            if proposal and proposal.get("sufficient"):
                step["decision"] = "continuar: paragem proposta pelo modelo REJEITADA (sem evidência para: " \
                                   + "; ".join(missing) + ")"
            else:
                step["decision"] = "continuar: falta evidência para " + "; ".join(missing)
            nq = _valid_query((proposal or {}).get("next_query"))
            if nq and nq not in tried and nq not in queue:
                queue.insert(0, nq)
                step["next_query"] = f"{nq} (proposta do modelo)"
            if ledger["calls"] >= MAX_MODEL_CALLS - 1:
                stop_reason = "limite de chamadas ao modelo (reservada a síntese)"
                break
        synth = {"raw": "", "seconds": 0.0, "error": None}
        if stop.is_set():
            report = {"final": "CANCELLED", "accepted": [], "rejected": [], "conflicts": [], "answer_lines": [],
                      "unanswered_parts": parts, "coverage": {}}
            stop_reason = "cancelado pelo operador"
        elif not cands:
            report = EV._compose({"accepted": [], "rejected": [], "conflicts": [], "coverage": {}, "final": "ABSTAIN",
                                  "schema_valid": None}, plan.question, parts)
        else:
            try:
                synth["raw"], synth["seconds"] = self._model(
                    EV.SYNTH_SYSTEM, EV.synthesis_prompt(plan.question, parts, cands), ledger)
            except ModelError as exc:
                synth["error"] = str(exc)
            report = EV.validate(synth["raw"], plan.question, parts, cands, kit.receipts, kit.kept)
        seconds = round(self.clock() - started, 2)
        state = State.TAREFA_CANCELADA if report["final"] == "CANCELLED" else FINAL[report["final"]]
        ignored = [t for d in EV.documents(kit.receipts, kit.kept) for t in d["ignored_instructions"]]
        meta = {"iterations": iterations, "stop_reason": stop_reason, "model_calls": ledger["calls"],
                "ignored_external_instructions": ignored,
                "model_seconds": round(ledger["seconds"], 2), "requests": guard.requests,
                "requests_avoided": self.policy.max_requests_per_mission - guard.requests}
        self._evidence(plan, params, cands, synth, report, kit, guard, seconds, meta)
        acc = report["accepted"]
        sources = [{"seq": r["seq"], "url": r["final_url"], "fetched_at": r["fetched_at"], "sha256": r["sha256"],
                    "bytes": r["bytes"], "supports": [f"A{i}" for i, a in enumerate(acc, 1) if a["seq"] == r["seq"]]}
                   for r in kit.receipts if r["tool"] == "web_open_public" and r["status"] == "OK"]
        lines = [f"Modo: {MODE_LABEL[self.policy.mode]}", f"Pergunta: {plan.question}",
                 "Partes a responder: " + "; ".join(parts), f"Plano: {plan.source}"]
        for s in iterations:
            lines.append(f"Iteração {s['iteration']}: «{s['query']}» → {len(s['opened'])} página(s); partes cobertas "
                         f"{len(s['coverage']['host_covered'])}/{len(parts)}; {s.get('decision', '')}")
        lines.append(f"Paragem: {stop_reason}; pedidos {guard.requests}/{self.policy.max_requests_per_mission}; "
                     f"chamadas ao modelo {ledger['calls']}")
        if report["final"] != "CANCELLED":
            lines.append("RESPOSTA (construída pelo anfitrião só com afirmações fundamentadas):")
            lines += [f"• {line}" for line in report["answer_lines"]]
        for i, rj in enumerate(report.get("rejected", []), 1):
            lines.append(f"REJEITADA: {str(rj.get('text') or rj.get('claim'))[:120]} — {rj['why']}")
        if ignored:
            lines.append(f"Instruções externas ignoradas (conteúdo não confiável nas fontes): {len(ignored)}")
        if report.get("conflicts"):
            lines.append("Conflitos indicados: " + "; ".join(report["conflicts"]))
        if report["final"] == "ABSTAIN":
            lines.append("O JARVIS abstém-se: evidência insuficiente nas fontes consultadas.")
        objectives = tuple((f"P{i + 1}", "COBERTA" if report["coverage"].get(i) else "SEM_EVIDENCIA",
                            (report["coverage"].get(i) or [{}])[0].get("seq")) for i in range(len(parts)))
        return TaskOutcome(state=state, capability=CAPABILITY,
                           operational_state=f"FREE_RESEARCH_{report['final']}_{self.policy.mode.upper()}",
                           verified=False, changes=None, objectives=objectives, receipts_count=len(kit.receipts),
                           receipt_events=tuple((r["seq"], r["tool"], r["status"]) for r in kit.receipts),
                           halt_reason_code="CANCELLED" if state == State.TAREFA_CANCELADA else "NONE",
                           error_code="NONE" if not synth["error"] else "MODEL_UNAVAILABLE",
                           model_commentary_unverified="", seconds=seconds, findings=tuple(lines),
                           sources=tuple(sources))

    def _evidence(self, plan, params, cands, synth, report, kit, guard, seconds, meta) -> Path | None:
        run = self.runtime / f"livre-{time.strftime('%Y%m%dT%H%M%S')}-{secrets.token_hex(3)}"
        try:
            (run / "pages").mkdir(parents=True, exist_ok=False)
            (run / "receipts.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kit.receipts))
            (run / "egress_audit.jsonl").write_text("".join(json.dumps(a, ensure_ascii=False) + "\n" for a in guard.audit))
            for seq, raw in kit.kept.items():
                (run / "pages" / f"{seq}.bin").write_bytes(raw)
            (run / "result.json").write_text(json.dumps({
                "version": "W3.2", "question": plan.question, "plan": plan.as_dict(), "plan_meta": params.get("plan_meta"),
                **meta, "candidates": [{k: c[k] for k in ("id", "seq", "entity", "section", "kind", "text", "scores")}
                                       for c in cands],
                "synthesis_raw": synth["raw"], "synthesis_error": synth["error"], "validation": report,
                "mode": self.policy.mode, "transport_guarantees": guarantees(self.policy), "model": self.model,
                "refused": [a for a in guard.audit if a.get("decision") == "REFUSED"],
                "timing": {"plan_s": (params.get("plan_meta") or {}).get("seconds"),
                           "network_s": round(sum(s.get("network_s", 0) for s in meta["iterations"]), 2),
                           "assess_s": round(sum(s.get("assess_s", 0) for s in meta["iterations"]), 2),
                           "synthesis_s": synth["seconds"], "mission_total_s": seconds}},
                ensure_ascii=False, indent=1, default=list))
        except OSError:
            return None
        self.last_run = run
        return run
