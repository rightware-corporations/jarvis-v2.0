# JRV-P1 — Control Plane: conversa e tarefa supervisionada numa única entrada de produto

**Branch:** `develop`.
- **Implementação:** `73b4c4d` (CP1).
- **Mostrar recibos e harness do ensaio:** `da3cb57`.
- **Ensaio real** em `da3cb57`, com a árvore limpa.

## 1. Arquitectura realmente integrada

```
INPUT (consola: python jarvis.py console [--tarefa-ensaio])
  → SESSION   TextFacade.open_session (efémera)                                  [existente]
  → ROUTE     texto livre → TaskEntry.submit_text → TextFacade (sem ferramentas)  [existente]
              /tarefas · /tarefa ID · /autorizar CÓDIGO (comandos exactos do anfitrião) [novo, consola]
  → AUTHORIZATION  ControlPlane: capacidade só se o anfitrião a activou no arranque;
                   código de uso único (6 hex, 120 s), consumido por qualquer tentativa  [novo]
  → EXECUTOR  TaskEntry.run_trusted_file_compare → AgentSession(allow={"files"})       [existente, TE-06A]
              → AgentPolicy (esquema, quotas, prazo, guarda de ciclos, auditoria)      [existente]
  → EVIDENCE  ReceiptLedger + evaluate_file_task (relê ficheiros, recalcula o diff)   [existente]
  → RESULT    ControlPlane.State + TaskOutcome (verificado só com COMPARISON_VERIFIED) [novo]
```

**Interfaces reutilizadas sem alteração:** `TextFacade`, `TaskEntry.submit_text`, `TaskEntry.run_trusted_file_compare` e o envelope que verifica, `AgentSession` (com `cancel`), `AgentPolicy`, `ReceiptLedger`, `FixtureWorkspace` e `evaluate_file_task`. Não foi criado nenhum orquestrador.

**Código novo ou alterado:**
- `rightware/control_plane.py` (novo);
- `rightware/console.py`: comandos de tarefa, flag do anfitrião, apresentação do resultado e dos recibos;
- `tests/test_p1_control_plane.py`;
- `labs/p1/mutation_p1.py` e `labs/p1/real_task_trial.py`.

**Inalterados:** `text_facade.py`, `task_entry.py`, `agent/*`, vendor e workflows.

## 2. Estados mostrados

| Estado | Quando |
|---|---|
| Resposta sem execução | Texto livre (o mesmo caminho e os mesmos rótulos da consola E0) |
| Tarefa não autorizada | Rota TASK de texto livre; capacidade inexistente ou não activada; código errado, expirado ou já usado; executor fora do envelope |
| Autorização necessária | `/tarefa ID` válido; mostra o código ao operador |
| Tarefa em execução | Depois de `/autorizar` |
| Execução parcial | Algum objectivo VERIFIED, mas não todos |
| Tarefa cancelada | Ctrl+C → `AgentSession.cancel` |
| Execução falhada | Estado ERROR do executor |
| Resultado verificado | Só COMPARISON_VERIFIED; as alterações vêm do código |
| Resultado desconhecido | Sem objectivos verificados (por exemplo, o modelo só afirma) |

## 3. Exemplo reproduzível (num computador autorizado com Ollama)

```bash
python jarvis.py console --model qwen3.5:4b --tarefa-ensaio
```

Na consola:
1. `/tarefas` (consulta as capacidades disponíveis);
2. `/tarefa comparar-versoes-ensaio` (pede a tarefa; devolve "Autorização necessária" e um código);
3. `/autorizar <código>` (autoriza explicitamente; a tarefa executa e mostra recibos, objectivos, alterações e o comentário do modelo como NÃO verificado);
4. `/sair`.

Sem `--tarefa-ensaio` não existe nenhuma tarefa. Os ficheiros são **sintéticos**: o anfitrião escreve-os numa pasta temporária e apaga-a no fim. Isto **não** é acesso a documentos reais.

## 4. Resultados

**FAKE/offline:**
- 18 testes P1;
- suite completa no venv fixado: **570 OK, 0 skipped** em `73b4c4d`;
- mutação: 16/16 mortos.

**Qwen real** (CPU sem GPU, Ollama 0.40.15 só em 127.0.0.1):

| Modelo | Pré-carregamento a frio | Autorização → resultado | Estado | Recibos | Narrativa do modelo |
|---|---|---|---|---|---|
| qwen3.5:4b `d8b0f5e9…` | 112 s | 45,2 s | **RESULTADO_VERIFICADO** (COMPARISON_VERIFIED) | #1 fixture_read A OK, #2 fixture_read B OK, #3 fixture_compare OK | Correcta (1 adição, 1 remoção, 1 modificação) |
| qwen3.5:2b `0689d440…` | 87 s | 20,3 s | **RESULTADO_VERIFICADO** | os mesmos 3 recibos | **Errada**: troca adicionado com modificado e diz que "notas" foi removido |

Em ambos:
- as alterações mostradas são as do código, verificadas: `receitas 100→120` modificada, `custos: 80` removida, `anexo: tabela 2` adicionada;
- o código de autorização foi lido do ecrã e escrito pelo operador simulado;
- o código de saída foi 0;
- a pasta de ensaio foi removida.

Evidência: `docs/evidence/p1/p1_real_supervised_task_2026-11-22.json`.

## 5. Limitações

- **Uma só capacidade, com ficheiros sintéticos.** Não há acesso a documentos reais, escrita, web nem Windows. O TE-06A só corre onde há abertura segura POSIX: no Windows, falha fechado.
- **Texto contraditório no comentário.** O `AgentSession` junta ao comentário do modelo a frase "Estado: não foi possível concluir o pedido com as ferramentas" mesmo quando o resultado está verificado. Está na secção "NÃO verificado" e não foi alterada, porque `agent/session.py` está protegido. Deve ser corrigida num pacote próprio.
- **Narrativa do 2B errada.** Com o 2B a narrativa saiu errada. O resultado verificado não depende dela, mas um utilizador pode ler o comentário: a separação visual é essencial.
- **Arranque a frio:** 87–112 s neste CPU, por isso o modelo deve ser pré-carregado.
- **Autorização local.** A autorização é do operador local da consola: o código é mostrado e escrito no mesmo terminal. Não há identidade multi-utilizador.
- **Amostra mínima:** uma execução real por modelo. Não é aceitação de E0/E1.

## 6. Próximo checkpoint (JRV-P2: adaptador Goose)

Ligar o executor goose (investigação TE-P2A/B/C/D da PR #27) como **segundo executor** atrás deste mesmo Control Plane: a mesma autorização do anfitrião e o mesmo vocabulário de estados, com o resultado derivado dos recibos do Gateway RIGHTWARE e do verificador.

Antes, é preciso:
- pré-registar o envelope do goose (ferramentas, rede, quotas e retoma);
- decidir como o código do laboratório entra em `develop`, num PR revisto e não por merge da PR #27;
- garantir que o percurso por omissão continua sem ferramentas.
