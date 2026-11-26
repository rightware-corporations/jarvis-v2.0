# JRV-INT01 — Integração final da pré-visualização pessoal

Ramo de integração B6. Baseline `7a91b86`. Data: 26/11/2026.
O Claude assumiu a engenharia (Manus indisponível), com autorização para editar `auth.py`, `gui/policy.py` e `bridge.py`. As políticas de segurança mantêm-se obrigatórias.
Classificação: **UNIT/FAKE** · **E2E REAL** (Chromium real, Qwen 2B real, STT/TTS reais; microfone simulado com fala sintética; sem túnel e sem rede) · **NÃO VERIFICADO**.

## A — Autenticação (ID01-A reproduzido)
- **GET** `/rw-login?t=…` em modo privado:
  - valida o link **sem o consumir** e mostra a página "Entrar no JARVIS" (sem script, sem recursos externos);
  - o CSRF vai no formulário;
  - cookie de desafio `rw_challenge`: HttpOnly, Secure, SameSite=Strict, `Path=/rw-login`, 300 s.
- **POST** `/rw-login`:
  - Origin exacta (`null`, ausente ou estranha são recusadas antes do handler);
  - formulário ≤ 1 KB; desafio de uso único; CSRF por `compare_digest`; prazo;
  - depois disso, o link é **consumido atomicamente** → 303 para `/` com o cookie de sessão Secure.
- **Replay:** um desafio usado ou um link usado → 403.
- **Modo local:** sem túnel, mantém o login GET antigo.
- **Causa do CROSS_ORIGIN:**
  - Um formulário HTML é uma navegação. Com `Referrer-Policy: no-referrer`, o browser envia `Origin: null` (especificação Fetch).
  - Os `fetch()` da aplicação (modo CORS) enviam sempre a origem real; por isso o chat funcionava.
  - **Correcção:** só a página de confirmação usa `strict-origin` (só a origem, nunca o caminho ou o token). `null` continua recusado.
  - **FACTO (Chromium real):** o POST do formulário levou `Origin: https://jarvis-e2e.example`.

## B — Identidade
- **Donos declarados pelo operador:** `--donos operador=lab:operador,issa=lab:issa`. Cada link pertence a um dono, e a sessão herda-o.
- **Transmissão do dono:** o bridge define `CURRENT_OWNER` a partir da sessão; o worker do `TextFacade` herda o contexto. A memória e os documentos usam `SessionOwner`. **O browser nunca escolhe o dono.** Sem dono, não há memória nem documentos.
- **Links seguintes sem rota de administração:** `python -m rightware.gui emitir-ligacao issa` (pedido local + SIGUSR1). O link fica em `.runtime/gui/session-url-issa` (0600) e nunca é impresso.

## C/D — Documentos e memória na interface
- **Rotas:** `DOCUMENT_ALLOW` e `MEMORY_ALLOW` só existem com a capacidade activa. Têm limites de corpo, com `Content-Length` obrigatório.
- **Interface:** botão **"Anexar documento"** (clipe) junto ao microfone, e painel **"Documentos e memória"**:
  - listar e eliminar documentos;
  - listar, corrigir e eliminar memórias.
  - A correcção usa as palavras escritas pelo utilizador, filtradas para dados sensíveis.
  - Não há aprendizagem automática.

## E — Inteligência documental (correcções delimitadas)
- **Percentagens:** recalculadas com a `CalculatorTool` fixada. Um valor errado é marcado no texto "⚠(não confirmado)" e o cálculo verificado é mostrado.
- **Valores atribuídos ao documento errado:** marcados.
- **Instruções maliciosas reproduzidas:** omitidas.
- **Frases só de localização** ("encontra-se na página 2") não contam como afirmações.

## F — Voz real
- **Causa das reticências permanentes, observada a 25/11:** o `transcribeAudio` original não tem timeout, por isso o estado "a transcrever" ficava para sempre se o pedido não tivesse resposta.
- **Paragem de 25/11:** o audit termina às 19:40:57 com `POST /v1/speech/transcribe ALLOW`, e os logs do servidor e do túnel param no mesmo minuto, sem erro. É compatível com a paragem do contentor cerca de 7 minutos depois de a sessão Claude ficar inactiva. Não é demonstrável.
- **Correcção:** patch declarado no overlay, `AbortSignal.timeout(45000)`. Em caso de erro aparece um aviso do upstream e o microfone volta a ficar livre. A conversa contínua já recuperava sozinha.
- **FACTO (E2E):** multipart WebM/Opus do MediaRecorder aceite (200; `Content-Length` presente), texto ditado no campo, reprodução 200, e conversa contínua com todas as fases.

## G — Aplicação unificada
- **Build:** `python -m rightware.gui frontend-build` recompila só o frontend (não recria o venv da voz) e grava `static/rw-build.json`. O estado (`/v1/rightware/state`) expõe `build.match`: o bundle corresponde ao código do overlay em execução.
- **E2E:** `labs/int01/run_e2e.sh` (servidor integrado em modo B6 + frente TLS local que não reescreve Host/Origin + Chromium real). Resultados em `docs/evidence/int01/`.

## H — Túnel
Preparado em `B6_TUNNEL_PROCEDURE.md` (secção INT01). **Não aberto.**
