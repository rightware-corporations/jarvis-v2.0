"""TE-06A demo: TASK -> PLAN -> TOOLS -> RESULTS -> VERIFICATION -> REPORT through the REAL JARVIS
executor with a FAKE model (no Ollama, no real Qwen). Creates two synthetic UTF-8 fixtures in a fresh
temporary directory, prints the structured JSON report and the readable text report, then deletes them.

Run (pinned venv): vendor/openjarvis/.venv/bin/python -m labs.te06a_files.demo
"""
from __future__ import annotations

import json
import pathlib
import tempfile

A_TEXT = "Relatório trimestral\nreceitas: 100\ncustos: 80\nnotas: nenhuma\nfim\n"
B_TEXT = "Relatório trimestral\nreceitas: 120\nnotas: nenhuma\nanexo: tabela 2\nfim\n"


def main() -> int:
    from labs.work07_r3c1.scenarios import FakeModel, call
    from rightware.agent.file_task import FixtureWorkspace, render_report
    from rightware.agent.session import AgentSession, Budgets
    from rightware.task_entry import TaskEntry, file_task_record
    from rightware.text_facade import TextFacade

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / "version_a.txt").write_text(A_TEXT, encoding="utf-8")
        (root / "version_b.txt").write_text(B_TEXT, encoding="utf-8")
        workspace = FixtureWorkspace(root, {"A": "version_a.txt", "B": "version_b.txt"}, max_bytes=16384)
        model = FakeModel([lambda m: call("fixture_read", file="A"), lambda m: call("fixture_read", file="B"),
                           lambda m: call("fixture_compare"),
                           lambda m: {"content": "Há 1 linha adicionada, 1 removida e 1 modificada."}])
        facade = TextFacade(adapter=object())
        sid = facade.open_session()
        try:
            def make_session():
                return AgentSession(model, "fake", allow={"files"}, confirm=lambda q: None, receipts=True,
                                    file_task="fixture-two-versions-compare", file_workspace=workspace,
                                    budgets=Budgets(max_calls=6, deadline_seconds=60), max_turns=6)
            result = TaskEntry(facade, file_session_factory=make_session).run_trusted_file_compare(
                sid, "Jarvis, compara as duas versões autorizadas deste documento, identifica as alterações e "
                     "apresenta um relatório.")
        finally:
            facade.close()
            workspace.close()
    record = file_task_record(result)
    print(json.dumps({k: v for k, v in record.items() if k != "generations"}, ensure_ascii=False, indent=2))
    print(render_report(record))
    return 0 if result.comparison_verified else 3


if __name__ == "__main__":
    raise SystemExit(main())
