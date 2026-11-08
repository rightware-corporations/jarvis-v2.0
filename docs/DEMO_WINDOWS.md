# Demonstração — Jarvis do Issa no Windows (≈15 min)

Só num PC Windows **autorizado pelo Issa**. Requisitos: Git, Python 3.10–3.13 x64, uv e Ollama já instalados; microfone e colunas; voz **Português (Portugal)** do Windows instalada. Modelo candidato do K03: `qwen3.5:4b` (o `qwen3.5:2b` fica como reserva se o PC for lento: trocar `-Model`).

Todos os comandos correm na pasta `jarvis-v2.0`, numa janela PowerShell normal (não é preciso administrador). `-ExecutionPolicy Bypass` vale só para esse comando e não altera o sistema.

## 0. Preparar (antes da demonstração)

```powershell
git clone --branch develop --recurse-submodules https://github.com/rightware-corporations/jarvis-v2.0.git
cd jarvis-v2.0
```

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File rightware\windows\Jarvis-Issa.ps1 -Mode install
```

```powershell
ollama pull qwen3.5:4b
```

Escrever `INSTALAR` quando pedido (instala só dependências Python dentro da pasta).

Numa **segunda janela**, deixar o Ollama a correr:

```powershell
$env:OLLAMA_NO_CLOUD = '1'; ollama serve
```

Verificação só de leitura (não abre nada, não grava áudio). Deve terminar em `SUMMARY: READY FOR REAL VALIDATION` / `RESUMO: sem FAIL`. Se `whisper_model` disser WARN, arrancar uma vez o modo voz para descarregar o modelo (~460 MB) antes da demonstração.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File rightware\windows\Jarvis-Issa.ps1 -Mode check -Model qwen3.5:4b
```

Fechar o Bloco de Notas e a Calculadora, se estiverem abertos. O Bloco de Notas do Windows 11 abre separadores no processo existente, e nesse caso o Jarvis diz honestamente «não consegui confirmar».

## 1. Identidade e contexto, por voz (sem acções)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File rightware\windows\Jarvis-Issa.ps1 -Mode voice -Model qwen3.5:4b
```

Enter numa linha vazia → falar → esperar a resposta falada:

1. «Quem és tu e para quem trabalhas?» → Jarvis, assistente pessoal do Issa, desenvolvido pela RIGHTWARE.
2. «Para este teste, o projecto Orion serve para gerir piscinas.»
3. «Qual é a capital de Moçambique?» → Maputo.
4. «Como se chama o projecto de que falei e para que serve?» → Orion, piscinas (contexto mantido).
5. «Abre o Bloco de Notas.» → **recusa**: as acções não estão autorizadas nesta sessão. Nada abre.
6. Fazer uma pergunta longa e carregar **Ctrl+C** enquanto pensa → «Cancelado.»; a sessão continua.
7. Dizer «sair».

## 2. Acções com autorização e confirmação

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File rightware\windows\Jarvis-Issa.ps1 -Mode actions -Model qwen3.5:4b
```

Escrever `AUTORIZO`. Depois, por voz:

1. «Abre o Bloco de Notas» → «Queres que eu abra o Bloco de Notas?» → «sim» → abre; «Confirmei que o processo está em execução».
2. «Abre a calculadora» → «não» → «Cancelado. Não abri a Calculadora.» Nada abre.
3. «Abre a calculadora» → «sim» → abre e é confirmada.
4. «Já abriste o Bloco de Notas?» → responde com base no resultado real; não abre nada novo.
5. «sair». O script mostra as linhas `AUDIT:` (acção, confirmação, resultado, PID): são a prova verificável.

## 3. Interromper e reiniciar

Fechar a janela do Jarvis (ou Ctrl+C na linha de entrada), voltar a correr o comando do passo 1 e fazer uma pergunta: o Jarvis arranca com o mesmo comando. Para o critério V12, repetir depois de reiniciar o PC.

## Evidência a entregar

- Os ficheiros `.runtime\logs\windows-*.log` e `diagnostic-*.json` (já sanitizados: sem utilizador, máquina, caminhos pessoais nem conversa).
- A tabela V1–V12 de `docs/WINDOWS_VOICE.md` preenchida.
- **Não** enviar gravações de voz nem conversas pessoais.
- Qualquer aplicação aberta **sem** «sim» = P0 NO-GO: parar e reportar.
