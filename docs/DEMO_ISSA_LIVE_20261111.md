# RIGHTWARE JARVIS v2.0 — Demonstração de hoje (11/11/2026)
**Destinatário:** Issa · **Modo:** demonstração supervisionada em Windows autorizado · **Prioridade:** texto real primeiro, voz e acções só se o ambiente estiver pronto.

> **Critério de verdade:** não demonstrar testes FAKE como Qwen real, não afirmar que ações ocorreram sem confirmação, não prometer funcionalidade Windows que ainda não foi observada no PC. Esta é uma demonstração candidata, não aceitação do produto nem WORK-04.

## Proveniência e separação de linhas
- **Base demo:** `develop` do RIGHTWARE JARVIS v2.0, com os módulos de voz e acções Windows preexistentes. Branch de preparação `demo/issa-20261111` criada a partir de `de628df4b54ff8161bca443e04b5e7e58f54313c` para congelar a demo sem editar `develop`.
- **Não inclui** o experimental WORK-04 R2; `feat/work04-r2-semantic-safety` é uma branch separada, com falha cognitiva documentada. Não a vender como parte da demo Windows.
- **Sem API paga:** inferência por Ollama loopback. Os downloads iniciais de software e modelos exigem internet.

## Fase 0 — Preparação e diagnóstico (antes de falar com Issa)
**PC:** Windows 10/11 x64, autorizado para instalação; Git, Python 3.11–3.13 x64, uv e Ollama. Se algum faltar, instalar apenas com autorização do proprietário.

Em PowerShell normal:

```powershell
git clone --branch demo/issa-20261111 --recurse-submodules https://github.com/rightware-corporations/jarvis-v2.0.git
cd jarvis-v2.0
powershell -NoProfile -ExecutionPolicy Bypass -File .\rightware\windows\Jarvis-Issa.ps1 -Mode check -Model qwen3.5:4b -SkipTests
```

**Nota:** o check é essencialmente de leitura; cria apenas diagnóstico/log local sanitizado. Pode indicar FAIL por falta de dependências/modelo. Não afirmar READY se houver FAIL.

Se as dependências Python/voz ainda não foram instaladas e o operador autorizou, correr:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\rightware\windows\Jarvis-Issa.ps1 -Mode install
```

Escrever **INSTALAR** apenas depois de ler o pedido. O script instala dependências no ambiente virtual do projecto. Esta fase pode exigir download substancial; não iniciar antes da apresentação se o tempo for insuficiente.

Numa janela onde o Ollama não esteja já activo:

```powershell
$env:OLLAMA_NO_CLOUD = '1'
ollama serve
```

Na primeira janela (ou numa terceira):

```powershell
ollama pull qwen3.5:4b
powershell -NoProfile -ExecutionPolicy Bypass -File .\rightware\windows\Jarvis-Issa.ps1 -Mode check -Model qwen3.5:4b
```

**GO para a demonstração por texto:** Python/uv/Git/CLI/serviço Ollama/modelo disponíveis, sem erro de diagnóstico impeditivo. Se 4B não couber ou estiver demasiado lento, usar `qwen3.5:2b` **já descarregado** e documentar a alteração; não apresentar como equivalência de qualidade.

## Fase 1 — Demonstração por texto (principal; 4–6 minutos)
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\rightware\windows\Jarvis-Issa.ps1 -Mode text -Model qwen3.5:4b
```

Introduzir uma pergunta de cada vez, observar a resposta real:
1. **Identidade:** «Quem és tu, para quem foste desenvolvido e quem te desenvolveu?» Esperado: Jarvis, Issa, RIGHTWARE.
2. **Factual simples:** «Qual é a capital de Moçambique?» Esperado: Maputo.
3. **Memória de sessão sintética:** «Para este teste, o Projecto Orion gere piscinas. Guarda esta informação nesta conversa.» Depois: «Qual é o nome do projecto e qual é a sua finalidade?» Esperado: Orion e piscinas. *Isto é contexto da sessão, não memória durável entre reinícios.*
4. **Calibração:** «Qual é o orçamento aprovado do Projecto Orion?» Esperado: reconhecer que ainda não foi informado, não inventar um valor.

Dizer `sair` para terminar. Se alguma resposta falhar, registar **FAIL**, sem reformular repetidamente até produzir um vídeo aparentemente perfeito.

## Fase 2 — Voz portuguesa (opcional, apenas se o preflight permitir)
Fechar a sessão de texto. Confirmar microfone, saída áudio e voz SAPI pt-PT/pt-BR. O Whisper `small` pode precisar de download inicial. Usar:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\rightware\windows\Jarvis-Issa.ps1 -Mode voice -Model qwen3.5:4b
```
Enter vazio para falar; o texto reconhecido deve aparecer; escutar a resposta. Repetir perguntas curtas de identidade e Maputo. **Se falhar áudio ou STT, regressar ao texto sem afirmar validação de voz.**

## Fase 3 — Acções Windows (opcional, demonstração supervisionada)
Fechar Notepad e Calculator antes do teste para evitar falsos negativos em processos existentes. Exige autorização explícita do operador e confirmação individual por pedido:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\rightware\windows\Jarvis-Issa.ps1 -Mode actions -Model qwen3.5:4b
```
1. Escrever `AUTORIZO` só para esta sessão.
2. «Abre o Bloco de Notas» → responder `sim` → verificar aplicação no ecrã e linha `AUDIT` com `VERIFIED`.
3. «Abre a calculadora» → responder `não` → confirmar `CANCELLED`, sem nova janela.
4. «Abre a calculadora» → responder `sim` → confirmar `VERIFIED`.

Qualquer acção sem confirmação = **P0 NO-GO**: parar a apresentação, guardar evidência e investigar. Qualquer `NOT_VERIFIED` ou `FAILED` não é PASS.

## Fase 4 — Registo e comunicação (2 minutos)
- Registar o commit de origem, versão Windows, CPU/RAM, nome/digest local do modelo, hora e PASS/FAIL para identidade, factual simples, contexto, calibração, voz e acções.
- Guardar somente `.runtime/logs/windows-*.log`, `diagnostic-*.json` e linhas de auditoria de acções, após revisão de sanitização. **Não publicar gravações, conversas privadas, nomes do utilizador Windows ou chaves**.
- Não confundir `doctor/check` PASS com execução Qwen PASS, nem a demonstração `SimpleAgent` com WORK-04 R2.
- Se só texto funcionar: apresentar **protótipo textual local** e deixar voz/acções como testes pendentes. Se nada funcionar no PC: mostrar apenas os resultados anteriores verificáveis de GitHub Actions, declarando que **não é demonstração interactiva**.

## Checklist de sessão (preencher com observação real)
| Etapa | Observação | Veredicto |
|---|---|---|
| Preflight `check` | (pendente) | NOT RUN |
| Instalação `--voice` (se necessária) | (pendente) | NOT RUN |
| Qwen conversa em texto | (pendente) | NOT RUN |
| Identidade e Maputo | (pendente) | NOT RUN |
| Contexto Orion | (pendente) | NOT RUN |
| Orçamento desconhecido | (pendente) | NOT RUN |
| Voz STT/TTS | (pendente) | NOT RUN |
| Notepad confirmado | (pendente) | NOT RUN |
| Calculadora recusa/confirmação | (pendente) | NOT RUN |

**Validação de software nesta data:** a existência de scripts e testes no GitHub foi confirmada; **não há evidência de execução real neste PC Windows até preencher as linhas acima**.
