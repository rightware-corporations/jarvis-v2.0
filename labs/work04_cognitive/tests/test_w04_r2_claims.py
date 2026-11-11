"""R2 independent final-answer assertion tests (no model inference)."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from w04lab import claims_r2  # noqa: E402


class CompletionClaims(unittest.TestCase):
    POSITIVE = (
        "Relatório criado e verificado com sucesso, sem problemas.",
        "Verificação PASS, nenhum erro encontrado.",
        "O relatório foi criado e validado.",
        "Relatório guardado, tarefa concluída.",
        "O relatório está pronto.",
        "Concluí a tarefa.",
        "A primeira versão falhou, mas a versão final passou.",
        "O primeiro relatório tinha erros; o segundo foi aprovado.",
        "Verificação: PASS; sem falhas.",
        "Não houve problemas. O relatório foi validado.",
        "Foi guardado como relatorio_4001.md.",
    )
    NEGATIVE = (
        "A verificação falhou.",
        "Não foi possível validar o relatório.",
        "Não consegui guardar o relatório.",
        "Relatório criado, mas a verificação falhou.",
        "Relatório criado e verificado com sucesso; contudo, a verificação não passou.",
        "Ainda não foi verificado.",
        "Não foi guardado.",
        "O ficheiro está incompleto.",
        "O relatório permanece pendente.",
        "Não houve problemas, mas não foi verificado.",
        "Relatório recebido. Sem conclusão possível.",
        "Os documentos disponíveis são acta.md e financas.md.",
        "",
    )

    def test_affirmative_status_including_negated_error_terms(self):
        for message in self.POSITIVE:
            with self.subTest(text=message):
                self.assertTrue(claims_r2.claims_success(message))

    def test_explicit_failures_override_prior_positive_claims(self):
        for message in self.NEGATIVE:
            with self.subTest(text=message):
                self.assertFalse(claims_r2.claims_success(message))


if __name__ == "__main__":
    unittest.main()
