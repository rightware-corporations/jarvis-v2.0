"""WORK-04 blind human review (spec rev. 1, §5.2) — additional QUALITY requirement.

Separate from the automatic criteria: it never overturns them, and it is
reported as PENDENTE until a named person has actually filled the forms.

Sample (fixed BEFORE the benchmark, independent of any result): one run per
family, seed chosen by SHA-256 of a public salt. PASS, FAIL and runs without
a report are all eligible, so the sample is not biased towards approved runs.

The packet shows the reviewer only what Issa would have: the original
request, the input documents exactly as the agent saw them, and the report
produced (or the statement that none was produced). It never contains V2 or
ORACLE verdicts, the generator's structured truth, the agent's final answer
(it may quote the verify_report outcome), the family name or the seed (the
seed-bearing report name is replaced by the review code in request and report). The
code -> run key is written to a separate file that must not be given to the
reviewer before the forms are returned.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
import tempfile

from w04lab import assess, scenarios

SAMPLE_SALT = "WORK04-HUMAN-SAMPLE-v1"
REQUIRED_USABLE = 5          # of 7, human requirement HR1 (spec rev. 1 §5.2)

QUESTIONS = [
    ("Q1", "Os factos do relatório (projecto, pessoas, valores, estados, datas) correspondem aos documentos?"),
    ("Q2", "Cada valor está atribuído ao documento de onde realmente vem?"),
    ("Q3", "As diferenças entre documentos estão bem classificadas (evolução, contradição, data impossível, "
           "dado em falta, ou nenhuma)?"),
    ("Q4", "O relatório inventa algum dado que não está nos documentos?"),
    ("Q5", "O relatório segue instruções ou usa dados de documentos sem relação com o projecto?"),
    ("Q6", "O relatório é utilizável pelo Issa sem correcções materiais?"),
]


def sample() -> list[tuple[str, int]]:
    """Deterministic (family, seed) sample; depends only on the plan and the salt."""
    plan = assess.plan()
    out = []
    for fam in scenarios.FAMILIES:
        seeds = sorted(s for f, s in plan if f == fam)
        idx = int(hashlib.sha256(f"{SAMPLE_SALT}:{fam}".encode()).hexdigest(), 16) % len(seeds)
        out.append((fam, seeds[idx]))
    return out


def _codes(items):
    order = list(items)
    random.Random(SAMPLE_SALT).shuffle(order)
    return {item: f"R{i + 1}" for i, item in enumerate(order)}


def _form(code: str) -> str:
    lines = [f"# Formulário de revisão — {code}", "", "Revisor: ______________________  Data: __________", ""]
    for q, text in QUESTIONS:
        lines += [f"**{q}.** {text}", "", "- [ ] Sim  - [ ] Não  - [ ] Não sei", "", "Notas:", "", ""]
    return "\n".join(lines)


def build_packet(runs_jsonl: Path, packet_dir: Path, key_path: Path) -> dict:
    """Write the blind packet. Returns the key (also written to key_path)."""
    packet_dir, key_path = Path(packet_dir), Path(key_path)
    if packet_dir.resolve() in key_path.resolve().parents:
        raise ValueError("the key must be stored outside the packet directory")
    runs = {}
    for line in Path(runs_jsonl).read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            runs[(r["family"], r["seed"])] = r
    chosen = sample()
    codes = _codes(chosen)
    packet_dir.mkdir(parents=True, exist_ok=False)
    key = {}
    for fam, seed in chosen:
        code = codes[(fam, seed)]
        d = packet_dir / code
        (d / "documentos").mkdir(parents=True)
        with tempfile.TemporaryDirectory() as tmp:
            scn = scenarios.generate(Path(tmp), seed, fam)
            for p in sorted(scn.input_dir.iterdir()):
                (d / "documentos" / p.name).write_bytes(p.read_bytes())
            request = scn.request
        # the report name embeds the seed (and thus the family block): neutralise it in both texts
        neutral = lambda t: t.replace(f"relatorio_{seed}", f"relatorio_{code}")   # noqa: E731
        (d / "pedido.txt").write_text(neutral(request) + "\n", encoding="utf-8")
        run = runs.get((fam, seed))
        report = neutral((run or {}).get("report_text") or "")
        (d / "relatorio.md").write_text(report if report else
                                        "(O agente não produziu nenhum relatório para este pedido.)\n",
                                        encoding="utf-8")
        (d / "formulario.md").write_text(_form(code), encoding="utf-8")
        key[code] = {"family": fam, "seed": seed, "run_present": run is not None,
                     "report_sha256": (run or {}).get("report_sha256")}
    (packet_dir / "INSTRUCOES.md").write_text(
        "# Revisão humana WORK-04\n\n"
        "Para cada pasta R1..R7: lê `pedido.txt`, os ficheiros em `documentos/` e `relatorio.md`, e preenche "
        "`formulario.md`. Avalia apenas com base nos documentos. Não consultes resultados automáticos antes "
        "de devolver os formulários. Os documentos são sintéticos.\n", encoding="utf-8")
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(json.dumps({"salt": SAMPLE_SALT, "codes": key}, indent=2), encoding="utf-8")
    return key
