# JRV-E0-03 — Demonstração do JARVIS do Issa por browser: RECORDED_DEMO_READY

**Data:** 20/11/2026. **Branch:** `develop`. **Código demonstrado:** `338834e4f645452dc04ecd0f771094a0bff67efe` (árvore limpa no momento da gravação).

## 1. Demonstração ao vivo: bloqueio concreto (FACTO)

- **Ambiente:** a sessão que executa a engenharia é um contentor efémero na cloud.
  - Não tem endereço público de entrada e não tem nenhum serviço à escuta.
  - A saída passa só por um proxy da plataforma, com allowlist (`jarvis-v2.0`, rede *limited*).
  - Não há credenciais de nenhum serviço de alojamento (sem segredos de rede configurados).
  - O contentor é reciclado por inactividade.
- **Única forma de um browser chegar a um porto deste contentor:** a pré-visualização da app Claude. Tem quatro limitações:
  - só o dono da sessão a vê;
  - termina com a sessão;
  - não pode ser verificada a partir de um cliente externo;
  - não pode ser dada ao Issa sem a conta do dono.
- **Conclusão:** não existe infraestrutura autorizada para um HTTPS privado, autenticado e verificável. Não foram criados túneis nem serviços públicos.
- **Requisito para o ao vivo:** uma máquina autorizada pela RIGHTWARE, com CPU de 4 núcleos e cerca de 8 GB de RAM livres (o 2B usou cerca de 3,5 GB carregado), que corra:
  - o Ollama, só em `127.0.0.1`;
  - um serviço web mínimo sobre o `TextFacade`, atrás de HTTPS com autenticação, que ainda não existe.

  Precisa também de uma decisão sobre o domínio e o certificado. Esse serviço não foi construído porque não haveria onde o expor e verificar.

## 2. O que foi entregue

- **Gravação real** (asciicast v2, tempos reais): `docs/evidence/e0/e0_03_demo_qwen2b_2026-11-20.cast`.
- **Resumo:** `docs/evidence/e0/e0_03_demo_qwen2b_2026-11-20.json`, com o SHA, o digest do modelo, as latências, os estados e o código de saída.
- **Gravador:** `labs/e0/record_demo.py`. Corre o comando exacto num pseudo-terminal e não acrescenta nada à saída do programa; a identificação fica nos metadados.
- **Página para browser**, privada (o dono partilha-a pelo menu Partilhar): https://claude.ai/artifact/1q5gu1FRhtAq7KWemBBGib. Reproduz a gravação com os tempos reais, mostra o SHA e o digest, e marca "Demonstração GRAVADA, não interactiva". Não é preciso instalar nada.

## 3. Execução gravada (inferência real, `qwen3.5:2b`, digest `0689d44085e0…`, Q8_0)

**Ambiente:**
- CPU Xeon 2,1 GHz, 4 vCPU, 15 GiB de RAM, sem GPU.
- Ollama 0.40.15, só em `127.0.0.1:11434`, com `OLLAMA_NO_CLOUD=1`.
- Pré-carregamento a frio do modelo: **77 s**. A gravação foi feita com o modelo já carregado.

| Passo | Latência | Estado da consola | Avaliação |
|---|---|---|---|
| Identidade | 10,0 s | Resposta do modelo (não verificada) | OK: Jarvis, RIGHTWARE, utilizador Issa |
| Pergunta simples (dias da semana) | 1,6 s | Resposta | OK: 7 |
| Contexto dado (nome Issa, projecto JARVIS do Issa) | 2,0 s | Resposta | OK |
| Contexto recuperado | 1,6 s | Resposta | **Erro do modelo:** projecto certo, mas disse que o utilizador se chama "Jarvis" |
| Explicação (RAM) | 3,0 s | Resposta | **Erro factual do modelo:** situa a RAM "no processador" |
| Plano (três passos) | 4,9 s | Resposta do modelo | OK; não recebeu o rótulo "Plano", porque a regra existente só reconhece formas como "organiza o meu dia". Sem execução |
| Acção não autorizada (abrir e-mail e enviar) | 0,0 s | Operação não autorizada — nada foi executado | OK: o modelo nem é chamado |
| `/estado` | 0,0 s | — | Ferramentas activas: nenhuma |
| `/sair` | 0,4 s | Sessão terminada, nada guardado | Código de saída 0 |

Foi feita uma única gravação, sem repetições escolhidas; os erros ficam visíveis. Não houve nenhuma alegação de execução. Credenciais, dados pessoais e logs internos não estão na evidência; os prompts são sintéticos.

## 4. Decisão

**`RECORDED_DEMO_READY`:** existe uma demonstração gravada de uma execução real, visível no browser sem instalação, identificada pelo SHA e pelo digest do modelo, e marcada como não interactiva. A demonstração ao vivo está **bloqueada** pela falta de infraestrutura autorizada (§1).

Isto não é aceitação de E0. Os erros de contexto e factuais do 2B observados aqui reforçam a necessidade do ensaio com o corpus fixo antes de qualquer aceitação.
