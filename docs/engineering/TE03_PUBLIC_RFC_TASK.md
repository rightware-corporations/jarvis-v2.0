# TE-03 — Primeira tarefa pública supervisionada do RIGHTWARE JARVIS

**Estado:** CANDIDATO / integração text-to-AgentSession implementada em branch de trabalho. Não aprovada para Issa nem produção.

## Objectivo
Permitir uma primeira tarefa multi-objectivo de leitura pública usando um **modelo Ollama local real**, sem substituir o OpenJarvis, e sem criar um executor genérico de shell/ficheiros.

A entrada `python jarvis.py task` é um opt-in explícito do host, **não** é um classificador automático de linguagem natural. O comando cria uma sessão temporária `TextFacade` e chama `TaskEntry.run_trusted_public_rfc_task`. A execução fica a cargo do `AgentSession` já existente no OpenJarvis/RIGHTWARE; o modelo só tem acesso às ferramentas `browse` aprovadas.

## Âmbito aprovado no código — exactamente este caso

- `www.rfc-editor.org` (HTTPS apenas), leitura pública de RFC 9110 e RFC 9112.
- `TaskContract` *code-owned* `rfc-9110-9112-public-readonly`, dois objectivos obrigatórios com URLs exactos.
- `AgentPolicy`: `allow={"browse"}`, `max_calls=10`, prazo 115 s, `max_turns=10`; sem WindowsActions, shell, FTP, browser com login, upload, ficheiro local, ou API paga.
- `ReceiptLedger` A2 e `completion_gate` A3 obrigatórios.
- O conteúdo de páginas é **dado não confiável**, nunca concede ferramentas adicionais.
- Os recibos provam que a operação de leitura ocorreu (sob condições de política e audit), mas não que o resumo do modelo seja correcto.
- O avaliador A3 para estes documentos **não comprova autenticidade**. Quando ambos são observados correctamente, o resultado de topo é `UNKNOWN_IDENTITY`, **não `COMPLETE_VERIFIED`**. O comando devolve exit code `3` para esse estado; este código indica revisão necessária, não inexistência de páginas lidas.

## Uso explícito, após setup e Ollama local

```powershell
python jarvis.py setup
ollama pull qwen3.5:2b
python jarvis.py task --allow-public-read --model qwen3.5:2b
python jarvis.py task --allow-public-read --model qwen3.5:2b --json
```

O serviço Ollama deve já estar activo em `127.0.0.1:11434`. **Isto não foi testado no dispositivo do Issa.** A capacidade de seguir ferramentas e interpretar português pelo Qwen só pode ser avaliada mediante execução real, fora dos testes mock. A flag deve ser intencional; sem ela o comando termina com código 2 e não inicializa inferência.

## Testes e evidência

- `tests/test_te03_public_task.py`: entrada host, negação do percurso texto, rejeição de cloud, fixture HTTP simulada, ambos objectivos observados/um em falta, tentativa de URL externo, restrições de `AgentSession`, saída JSON com modelo FAKE.
- Os testes exercitam a implementação real de `AgentSession` com modelo `FakeModel`, nunca chamam Ollama ou RFC Editor.
- Suite completa: `vendor/openjarvis/.venv/bin/python -m unittest discover -s tests -v`; zero skips esperados no ambiente vendor fixado.
- A prova live de Qwen, quando executada, tem de preservar modelos, URLs, saídas, SHA, restrições e FAIL/INCOMPLETE/UNKNOWN. Um workflow bem-sucedido não significa que os dois objectivos foram cumpridos.

## Limitações e próximos gates

1. A1 verifica apenas URLs e evidência técnica, não identidade do documento original nem veracidade do resumo.
2. A tarefa multi-objectivo em URLs públicos testa sobretudo function-calling. Não demonstra diagnóstico Windows, comparações de ficheiros ou autonomia geral.
3. TextFacade e CLI ainda são dois percursos diferentes; `task` faz explicitamente opt-in e não permite que texto comum active ferramentas.
4. Cancelamento e retry após timeout de ferramentas exigem revisão adicional antes de operações consequenciais.
5. Sem memoria durável, recomeço após falha, interface gráfica, voz, Goose, Agent Zero ou Hermes.
6. Branch TE-03 está empilhada sobre TE-02 (PR #13), que por sua vez depende de D01/D02 (PR #11). Não integrar/merge até revisão independente e estado CI final.

**Próximo passo de produto:** aceitar apenas a prova do ciclo de tarefa sobre fontes públicas, verificar comportamento com Qwen real e então decidir se a capacidade existente basta ou se o novo módulo goose é necessário.
