# RIGHTWARE Jarvis v2.0

Jarvis do Issa: assistente pessoal destinado ao Issa, desenvolvido pela RIGHTWARE com base no OpenJarvis e inferência local via Ollama. Estado: **fundação em desenvolvimento**, não release nem assistente Windows validado.

## Estrutura

| Pasta | Responsabilidade |
|---|---|
| `vendor/openjarvis` | Código upstream completo como submódulo Git, fixado a uma revisão |
| `rightware` | Arranque e futuras integrações RIGHTWARE |
| `configs` | Perfil português, Ollama local, analytics desligadas |
| `docs` | Decisões, evidência e continuidade |
| `tests` | Verificações dirigidas da camada RIGHTWARE |

O projecto anterior continua em https://github.com/rightware-corporations/jarvis. Não foi alterado.

## Arranque por texto

Requisitos: Git, Python **3.11–3.13**, [uv](https://docs.astral.sh/uv/getting-started/installation/) e [Ollama](https://ollama.com/download). Acesso GitHub ao repositório RIGHTWARE. Downloads iniciais exigem internet. `setup` instala só o núcleo Python, sem GUI/voz/Rust opcional.

```sh
git clone --branch develop --recurse-submodules https://github.com/rightware-corporations/jarvis-v2.0.git
cd jarvis-v2.0
python jarvis.py setup
ollama pull qwen3.5:2b
python jarvis.py doctor
python jarvis.py chat
```

O Ollama deve estar a correr em `127.0.0.1:11434`. Para desactivar também o serviço cloud do **servidor Ollama**, definir `OLLAMA_NO_CLOUD=1` no processo que o inicia, por exemplo numa janela PowerShell dedicada:

```powershell
$env:OLLAMA_NO_CLOUD = '1'
ollama serve
```

Se o Ollama já estiver em execução, configurar/reiniciar esse processo; definir a variável apenas no cliente não altera um servidor existente. Não executar uma segunda instância na mesma porta.

O lançador usa o agente `simple`, sem ferramentas de efeitos. Não necessita de chave Claude, Gemini ou OpenAI. Remove variáveis de credenciais cloud do processo filho. Isto não constitui isolamento de rede nem auditoria de todos os caminhos upstream. As integrações cloud continuam disponíveis no código upstream, mas não são seleccionadas neste percurso.

A configuração inicial é copiada para `.runtime/openjarvis/config.toml`, sem substituir uma configuração existente. `agent.default_system_prompt` define a identidade neste modo. Não é garantia contra alucinações.

`doctor` verifica revisão, CLI, serviço local e presença do modelo; **não faz inferência**. `chat` termina com `/quit`; Ctrl+C interrompe a sessão. Os logs de instalação ficam em `.runtime/logs/`; o wrapper não grava transcrições de conversa. O armazenamento efectuado pelo próprio upstream deve ser revisto antes de uso com dados pessoais.

Para comparar outro modelo **já descarregado**:

```sh
python jarvis.py chat --model NOME_DO_MODELO_LOCAL
```

A escolha definitiva do modelo está pendente. O Qwen3.5 2B é apenas a referência inicial. Kaggle serve de laboratório temporário, não de disponibilidade permanente do produto.

## Laboratório GPU sem token — recomendado

**O teste inicial para escolher o motor não exige token GitHub nem upload do repositório privado.** Utiliza [qa/JARVIS_ISSA_KAGGLE_NO_TOKEN.ipynb](qa/JARVIS_ISSA_KAGGLE_NO_TOKEN.ipynb), com **uma única célula Python**. O notebook clona apenas o OpenJarvis público na revisão fixada, configura a identidade de Jarvis do Issa, obtém Ollama v0.40.15 (SHA-256 verificado), descarrega os modelos Qwen3.5 2B/4B e testa seis perguntas com contexto e uma calculadora real num agente independente. Exporta um ZIP de evidências.

**Execução:** descarregar o notebook do repositório usando a sessão autenticada do browser, importar no Kaggle, activar Internet + GPU T4 e executar a única célula. Não configurar GITHUB_TOKEN, não inserir credenciais e manter o notebook privado. Os prompts Orion são sintéticos e não contêm dados pessoais reais.

**Limite crucial:** este é um ensaio do **upstream público OpenJarvis**, não da integração privada RIGHTWARE. Selecciona o modelo a partir de evidência e depois valida o launcher RIGHTWARE num ambiente autorizado. Sem executar GPU real, o estado permanece NOT RUN.

## Laboratório privado com autenticação (alternativa, não recomendada neste momento)



A alternativa de comparação integrada no wrapper privado está preparada em [qa/JARVIS_ISSA_KAGGLE.ipynb](qa/JARVIS_ISSA_KAGGLE.ipynb). O notebook clona `develop` com submódulos, instala as dependências fixadas, inicia Ollama **v0.40.15** em loopback, obtém os modelos e executa [qa/compare_models.py](qa/compare_models.py). A sessão utiliza seis perguntas sintéticas e uma prova separada de ferramenta; os resultados são gravados em JSON e ZIP.

Para executar: abrir/importar o notebook no Kaggle, activar **Internet** e **GPU**, definir em Kaggle Secrets um `GITHUB_TOKEN` com acesso somente de leitura ao repositório privado, e executar as três células por ordem. O token não deve ser partilhado nem incluído em comandos ou outputs. Se a pasta `/kaggle/working/jarvis-v2.0` já existir, o notebook **não** faz actualização silenciosa. Confirmar que o SHA mostrado é a revisão que se pretende testar.

**Ainda não executado na GPU após esta publicação.** CI aprova a sintaxe do notebook e os testes locais de preflight, não a inferência com Qwen. A comparação apenas é concluída quando o ZIP contém transcrições, SHA, ambiente, tempos e `tool_results` auditáveis. O Kaggle não testa microfone, altifalantes ou aplicações Windows.

## Desenvolvimento

Apenas `main` e `develop`; alterações em `develop`, revisão por PR para `main`. O submódulo permite preservar o upstream e actualizar com rastreabilidade. Um download ZIP do repositório não inclui automaticamente o submódulo: utilizar a clonagem acima.

```sh
python -m unittest discover -s tests -v
```

Consultar [handoff](docs/HANDOFF.md), [arquitectura](docs/ARCHITECTURE.md) e [proveniência](UPSTREAM_PROVENANCE.md). A primeira entrega é texto funcional; voz, wake word, memória durável e acções Windows continuam pendentes.
