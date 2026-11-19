# JRV-TE-P2D — Desenho do egress público supervisionado e da verificação de investigação (GATE 1)

Data: 2026-11-19. Branch `exp/te-p1-kaggle-goose`, Draft PR #27. Base `cf096df`.

## 1. Factos do ambiente que condicionam o desenho (FACTO)

- **Sem DNS e sem rota directa.** Este contentor não tem DNS (`getent hosts docs.python.org` vazio) e toda a saída passa pelo proxy de egress da plataforma em `127.0.0.1:<porta>` (MITM com CA própria e allowlist de hosts própria).
- **Recusa na plataforma.** O proxy recusou `docs.python.org` (CONNECT 403). Pedi a alteração do ambiente, que foi aprovada e funcionou durante alguns minutos (preparação: `crypto.html` 200, `secrets.html` 200, `/3/library/secrets` 301). Depois o host **desapareceu da lista do ambiente** e voltou a 403. Não voltei a pedir nem contornei a recusa.
- **O fetcher de produção falha fechado.** O `HttpxFetcher` de produção (`rightware/agent/web.py`, congelado) usa um guard SSRF baseado em DNS: o `check_ssrf` do OpenJarvis, o resolver fixo e o `is_global` do par TCP. Neste ambiente falha fechado ("Could not resolve host"), e **assim deve continuar**: não foi alterado, nem lhe foram dados IPs falsos.

## 2. Arquitectura

```
goose (jrv-agent --internal, IP fixo, sem rota)
  └─MCP→ Gateway (só jrv-agent --internal; sem rota; AgentPolicy, recibos, PublicBrowser com allowlist)
           └─ EgressFetcher → 1 socket Unix (/egress/egress.sock, directório dedicado montado só-leitura)
                 └─ serviço de egress RIGHTWARE no HOST (labs/te_p2d_public/egress.py)
                       └─ proxy de egress da plataforma (CONNECT, TLS verificado com a CA da plataforma)
                             └─ docs.python.org (só /3/library/)
```

- O goose e o Gateway não têm caminho de rede para fora. Isto é **demonstrado** em cada ensaio por sondas executadas antes do goose: acesso directo ao host público, à internet e à porta do proxy no host a partir da rede do agente, e acesso directo a partir de dentro do Gateway. Tudo tem de dar BLOCKED. O egress tem de recusar outro host e outro caminho. Qualquer falha nas sondas é STOP.
- O Gateway continua a expor apenas `web_open`, `web_follow`, `web_find` e `submit_report`; mantém-se o filtro bidireccional de ferramentas no model tap.

## 3. Política de egress (pura, aplicada duas vezes: no Gateway antes de enviar e no serviço antes de ligar)

- Só `https`; porta 443; GET; sem credenciais no URL; sem IPs literais.
- Host **exactamente** na allowlist (`docs.python.org`), o que exclui subdomínios e sufixos.
- Caminho dentro dos prefixos permitidos (`/3/library/`); sem `.`/`..`, sem `%2e`/`%2f`, sem barras invertidas nem caracteres de controlo; comprimento máximo de 2048.
- O `check_ssrf` do OpenJarvis continua a ser consultado. Qualquer veredicto diferente do "Could not resolve host" esperado para o nome exactamente permitido leva a recusa.
- **Redireccionamentos:** o serviço nunca os segue. O Gateway volta a verificar cada salto (allowlist do browser e política) antes de pedir de novo; máximo de 5 saltos.
- **Ligação efectiva (por resposta):**
  - o par TCP tem de ser exactamente o proxy da plataforma configurado;
  - o certificado TLS tem de ser válido para o host pedido (verificação do httpx com a CA da plataforma);
  - SANs e emissor ficam registados no log.
- **Limites:**
  - timeout de 15 s;
  - corpo descomprimido até 1 MB (corta bombas de compressão);
  - só `text/html` e `text/plain`;
  - orçamento por ensaio de 12 pedidos e 3 MB;
  - sem cookies, cabeçalhos fixos, sem corpo do pedido.
- **Integridade:** o SHA-256 do corpo é enviado pelo serviço e recalculado no Gateway. Uma diferença dá recusa.
- **Evidência:** cada decisão (OK, REFUSED ou FAILED) fica em `egress.jsonl`, que é o log independente do lado do host.

### Limite honesto (NÃO VERIFICÁVEL neste ambiente)

A verificação ao nível do IP de origem (anti-rebinding, `is_global` do par) não é possível: a resolução de nomes e a ligação à origem pertencem ao proxy da plataforma. É substituída, para este piloto, por:
- allowlist de um único host exacto em dois pontos independentes;
- allowlist da própria plataforma;
- par TCP fixo no proxy;
- verificação do certificado TLS para o host exacto.

O `HttpxFetcher` de produção continua a exigir as camadas de IP onde há DNS.

## 4. Conteúdo hostil

- O HTML é reduzido a texto pelo parser da biblioteca padrão.
- O texto é emoldurado como dado não confiável com uma fronteira aleatória, e os marcadores semelhantes à moldura são neutralizados (lógica existente e inalterada).
- Instruções nas páginas não criam permissões: as ferramentas são decididas pela AgentPolicy.
- Texto que imita observações RIGHTWARE não cria evidência: o verificador usa apenas as observações registadas pelo Gateway (por sequência de recibo).

## 5. Contrato `te-p2d.research.v1` e verificação

- **Observações:** cada leitura com sucesso é anunciada ao modelo como `[RIGHTWARE observação <seq> | sha256 <16> | <url>]`. O Gateway guarda o texto exacto mostrado e o respectivo hash.
- **Contrato (estrutural):** `question_id`, `answer`, `abstained`, `claims[]` (`claim_id`, `text`, `source_url`, `observation`, `quote`), `sources[]` e `limitations`, com as regras estritas de te-p2b. Não contém nenhum valor da pergunta (teste canário).
- **Verificador independente (`research_verify.py`):**
  1. entrega pelo canal com recibo;
  2. correspondência egress↔recibos exacta e nenhum pedido fora da política;
  3. observação válida: recibo executado, BOUND, auditado, HTTP 200, hash raw igual e hash do texto igual;
  4. afirmação creditada só se o URL for o da observação citada e o excerto (≥ 12 caracteres, espaços e maiúsculas normalizados) existir no texto mostrado;
  5. todas as fontes têm de ter sido observadas;
  6. rubrica semântica pré-registada com referência protegida (`reference_q_py_01.json`, nunca mostrada ao modelo): cada facto tem de estar na resposta E numa afirmação creditada (texto e excerto), e a fonte exigida tem de ser citada.
- **Veredictos:** `RESEARCH_VERIFIED_LIMITED`, `ABSTAINED` ou `NOT_VERIFIED`. A verificação de fontes prova o que foi **lido e citado**, não que cada frase seja verdadeira.

## 6. Decisão GATE 1

Os limites exigidos são garantidos por construção e testados offline (30/30 mutantes mortos). A única camada não verificável (IP de origem) está declarada e substituída por controlos mais estreitos. **Implementação aprovada para piloto experimental.** O egress real só é activado se a política de rede da plataforma permitir o host pré-registado; neste momento não permite.
