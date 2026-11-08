# RIGHTWARE Jarvis v2 — continuidade

## Decisão desta sessão

O utilizador forneceu `rightware-corporations/jarvis-v2.0` para concretizar a implementação separada baseada no OpenJarvis. O projecto anterior `rightware-corporations/jarvis` deve ser preservado. Branches: main e develop. Produto independente do Claude no runtime; modelo local ou auto-hospedado, sem API paga obrigatória.

## Evidência anterior, não reexecutada por esta fundação

Ensaio OpenJarvis/Qwen3.5 2B/Ollama 0.40.15 em CPU: conversa, resposta Maputo, recordação parcial de Orion e ferramenta calculator real (137 × 29 = 3973). Personalização de identidade funcionou com agent.default_system_prompt. Houve invenções sobre Orion; fidelidade não aprovada. O ensaio anterior resolveu dependências no momento; esta fundação usa uv.lock upstream com --frozen, pelo que uma nova prova real é necessária.

Mark XXXIX-OR foi investigado: Gemini Live/OpenRouter, sem percurso Ollama encontrado e README com uso não comercial. Não foi importado.

## Implementado

- Upstream fixado em submódulo, atribuição e licença.
- Camada RIGHTWARE de setup/doctor/chat; configuração portuguesa.
- Logs de instalação e remoção de credenciais cloud do ambiente filho.
- Quatro testes dirigidos de configuração/encaminhamento.
- Workflow leve para estes testes; não é CI de inferência nem suite upstream.

## Limites

Sem migração da camada Wyzer. Sem voz, GUI, wake word, acções Windows ou memória persistente validados. Não chamar esta etapa release. OLLAMA_NO_CLOUD no cliente não reconfigura um daemon já existente. O Kaggle é laboratório temporário. Não instalar no PC do destinatário por inferência.

## Próxima execução

1. Clonar develop com submódulos; executar setup e doctor com Ollama local.
2. Executar o corpus curto com modelo real e preservar respostas/tempos por SHA.
3. Comparar uma alternativa de modelo no mesmo ambiente; escolher pelo resultado, não apenas tamanho.
4. Só depois integrar voz e tarefas no Windows autorizado.

Consultar docs/VALIDATION.md para o que foi efectivamente validado nesta entrega. Actualizar este ficheiro após cada resultado material.
