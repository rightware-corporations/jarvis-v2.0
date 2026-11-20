# Arquitectura inicial

Estado: implementação mínima de arranque; expansão futura condicionada a evidência.

1. `jarvis.py` delega em `rightware.runtime`.
2. O runtime verifica a revisão upstream, prepara configuração e inicia a CLI original.
3. OpenJarvis gere a conversa com agente `simple` e consulta Ollama em loopback.
4. O modelo é substituível; a configuração portuguesa não altera pesos.

A primeira etapa não adiciona outro orquestrador, serviço HTTP ou base de dados. Preservamos a implementação upstream em vez de duplicar contexto e políticas.

Fronteiras futuras: modelo/contexto; voz/interface; política/acções; evidência. Só criar módulos adicionais quando houver funcionalidade real. As regras de confirmação do projecto Wyzer são referência, não um conjunto já migrado. Não copiar os testes antigos e apresentá-los como cobertura do OpenJarvis.

## Objectivo de dois dias

É um limite de escopo/esforço pretendido, não garantia de calendário. Primeiro: conversa e comparação de modelos. Depois: voz e poucas tarefas autorizadas, sujeitas ao equipamento de destino. Sem treino, redesign completo ou grande refactor nesta etapa.

## Critérios do próximo ensaio

Mesmo corpus para o modelo inicial e uma alternativa mais capaz: identidade, Orion com factos conhecidos/desconhecidos, mudança de assunto e recuperação, cálculo via ferramenta e ausência de afirmações falsas de execução. Medir latência, RAM/VRAM e falhas; uma demonstração isolada não dá uma probabilidade de fiabilidade. Não executar ferramentas Windows no Kaggle nem confundir simulação com sucesso real.
