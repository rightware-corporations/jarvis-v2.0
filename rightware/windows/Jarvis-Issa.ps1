<#
.SYNOPSIS
  RIGHTWARE — Jarvis do Issa: verificação, instalação autorizada e arranque no Windows.

.DESCRIPTION
  Modo por omissão "check": SÓ LEITURA. Não instala, não altera o sistema, não abre
  aplicações, não grava áudio. Os outros modos pedem confirmação escrita.

    check    Ferramentas, Ollama, áudio, voz portuguesa, diagnóstico Python, testes unitários
    install  python jarvis.py setup --voice  (só depois de escrever INSTALAR)
    text     Jarvis por teclado, respostas no ecrã (sem microfone, sem acções)
    voice    Jarvis por voz (microfone + voz SAPI), sem acções Windows
    actions  Voz + Bloco de Notas/Calculadora (escrever AUTORIZO; cada acção pede "sim")

  Logs sanitizados (sem utilizador, máquina, caminhos pessoais nem conversas):
  .runtime\logs\windows-<modo>-<UTC>.log

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File rightware\windows\Jarvis-Issa.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File rightware\windows\Jarvis-Issa.ps1 -Mode voice
#>
[CmdletBinding()]
param(
  [ValidateSet('check', 'install', 'text', 'voice', 'actions')]
  [string]$Mode = 'check',
  [string]$Model = '',
  [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $Root
# Process-scoped only: UTF-8 for Python and for captured output. No system change.
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$LogDir = Join-Path $Root '.runtime\logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$LogFile = Join-Path $LogDir "windows-$Mode-$Stamp.log"
$Summary = New-Object System.Collections.ArrayList

function Protect-Text([string]$Text) {
  if ($null -eq $Text) { return '' }
  # Order matters: the repo path usually sits inside the user profile.
  $values = @($Root, $env:USERPROFILE, $env:USERNAME, $env:COMPUTERNAME)
  $tokens = @('<REPO>', '<HOME>', '<USER>', '<HOST>')
  for ($i = 0; $i -lt $values.Count; $i++) {
    if ($values[$i] -and $values[$i].Length -gt 1) {
      $Text = $Text.Replace($values[$i], $tokens[$i])
    }
  }
  return $Text
}

function Write-Log([string]$Text) {
  Write-Host $Text
  Add-Content -Path $LogFile -Value (Protect-Text $Text) -Encoding UTF8
}

function Add-Result([string]$Status, [string]$Name, [string]$Detail) {
  [void]$Summary.Add([pscustomobject]@{ Status = $Status; Check = $Name })
  Write-Log ("[{0}] {1}: {2}" -f $Status, $Name, $Detail)
}

function Invoke-Native([string]$Exe, [string[]]$Arguments) {
  # Native stderr must not become a terminating error under 'Stop'.
  $previous = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    $output = & $Exe @Arguments 2>&1 | ForEach-Object { "$_" } | Out-String
    return [pscustomobject]@{ Code = $LASTEXITCODE; Output = $output.Trim() }
  } catch {
    return [pscustomobject]@{ Code = -1; Output = "$_" }
  } finally {
    $ErrorActionPreference = $previous
  }
}

function Find-Python {
  # Accept 3.10–3.13 x64; ignore the Microsoft Store "python" alias stub.
  # Windows PowerShell 5.1 does not escape embedded double quotes in native
  # arguments, so the probe below deliberately contains no quotes at all.
  $probeCode = 'import sys,struct;print(sys.version_info[0],sys.version_info[1],struct.calcsize(chr(80))*8)'
  foreach ($candidate in @('python', 'py -3.13', 'py -3.12', 'py -3.11', 'py -3.10')) {
    $c = $candidate.Split(' ')
    $exe = $c[0]
    $prefix = @($c | Select-Object -Skip 1)
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    $r = Invoke-Native $exe ($prefix + @('-c', $probeCode))
    if ($r.Code -ne 0) { continue }
    $parts = @($r.Output.Trim().Split(' '))
    if ($parts.Count -ne 3) { continue }
    if ($parts[0] -eq '3' -and [int]$parts[1] -ge 10 -and [int]$parts[1] -le 13 -and $parts[2] -eq '64') {
      return [pscustomobject]@{ Exe = $exe; Prefix = $prefix; Version = "3.$($parts[1])" }
    }
  }
  return $null
}

function Test-Tool([string]$Name, [string[]]$VersionArgs, [string]$Hint) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    Add-Result 'FAIL' $Name "não encontrado -> $Hint"
    return $false
  }
  $r = Invoke-Native $Name $VersionArgs
  $first = ($r.Output -split "`n")[0]
  if ($r.Code -eq 0) { Add-Result 'PASS' $Name $first; return $true }
  Add-Result 'FAIL' $Name "erro ($($r.Code)): $first"
  return $false
}

function Get-LocalJson([string]$Path) {
  $client = New-Object System.Net.WebClient
  $client.Proxy = $null          # loopback only, never through a proxy
  try { return ($client.DownloadString("http://127.0.0.1:11434$Path") | ConvertFrom-Json) }
  finally { $client.Dispose() }
}

function Invoke-Jarvis([string[]]$JarvisArgs) {
  $all = @($Python.Prefix) + @('jarvis.py') + $JarvisArgs
  Write-Log ("RUN: python " + (($all | Select-Object -Skip $Python.Prefix.Count) -join ' '))
  & $Python.Exe @all
  return $LASTEXITCODE
}

function Confirm-Word([string]$Question, [string]$Word) {
  Write-Host ""
  Write-Host $Question -ForegroundColor Yellow
  $answer = Read-Host "Escreve $Word para continuar (qualquer outra resposta cancela)"
  return ($answer -ceq $Word)
}

function Write-ActionAudit([datetime]$Since) {
  $files = Get-ChildItem -Path $LogDir -Filter 'actions-*.jsonl' -ErrorAction SilentlyContinue
  $count = 0
  foreach ($f in $files) {
    foreach ($line in Get-Content -Path $f.FullName -Encoding UTF8) {
      try { $rec = $line | ConvertFrom-Json } catch { continue }
      $when = $rec.utc   # PowerShell 7 already converts ISO dates; 5.1 does not
      if ($when -isnot [datetime]) {
        $when = [datetime]::Parse($when, [Globalization.CultureInfo]::InvariantCulture)
      }
      if ($when.ToUniversalTime() -ge $Since) {
        Write-Log ("AUDIT: action={0} authorized={1} confirmed={2} outcome={3} pid={4}" -f `
          $rec.action, $rec.authorized, $rec.confirmed, $rec.outcome, $rec.pid)
        $count++
      }
    }
  }
  Write-Log "AUDIT: $count acção(ões) registada(s) nesta sessão."
}

# ---------------------------------------------------------------------------
Write-Log "=== RIGHTWARE — Jarvis do Issa | modo: $Mode | $Stamp ==="
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
if ($os) { Write-Log ("Windows: {0} {1} ({2})" -f $os.Caption, $os.Version, $os.OSArchitecture) }
$sha = Invoke-Native 'git' @('rev-parse', 'HEAD')
if ($sha.Code -eq 0) { Write-Log "REPO SHA: $($sha.Output)" }

$Python = Find-Python
if ($Python) { Add-Result 'PASS' 'python' "$($Python.Exe) $($Python.Prefix -join ' ') -> $($Python.Version) x64" }
else { Add-Result 'FAIL' 'python' 'Python 3.10–3.13 x64 não encontrado -> https://www.python.org/downloads/windows/' }

if ($Mode -eq 'check' -or $Mode -eq 'install') {
  [void](Test-Tool 'git' @('--version') 'https://git-scm.com/download/win')
  [void](Test-Tool 'uv' @('--version') 'https://docs.astral.sh/uv/getting-started/installation/')
  [void](Test-Tool 'ollama' @('--version') 'https://ollama.com/download/windows')

  try {
    $v = Get-LocalJson '/api/version'
    $tags = Get-LocalJson '/api/tags'
    $names = @($tags.models | ForEach-Object { $_.name })
    Add-Result 'PASS' 'ollama_service' ("versão {0}; modelos: {1}" -f $v.version, ($names -join ', '))
  } catch {
    Add-Result 'FAIL' 'ollama_service' 'não responde em 127.0.0.1:11434 -> noutra janela: $env:OLLAMA_NO_CLOUD=1; ollama serve'
  }

  $endpoints = @(Get-CimInstance Win32_PnPEntity -Filter "PNPClass='AudioEndpoint'" -ErrorAction SilentlyContinue |
                 Where-Object { $_.Status -eq 'OK' } | ForEach-Object { $_.Name })
  if ($endpoints.Count -gt 0) { Add-Result 'PASS' 'audio_endpoints' ($endpoints -join '; ') }
  else { Add-Result 'WARN' 'audio_endpoints' 'nenhum dispositivo de áudio activo (microfone/colunas)' }

  try {
    Add-Type -AssemblyName System.Speech
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $voices = @($synth.GetInstalledVoices() | Where-Object { $_.Enabled } | ForEach-Object { $_.VoiceInfo })
    $synth.Dispose()
    $pt = @($voices | Where-Object { $_.Culture.Name -like 'pt-*' } | ForEach-Object { "$($_.Culture.Name) $($_.Name)" })
    if ($pt.Count -gt 0) { Add-Result 'PASS' 'portuguese_voice' ($pt -join '; ') }
    else { Add-Result 'WARN' 'portuguese_voice' ("nenhuma voz pt ({0} outras). Definições > Hora e idioma > Idioma > Português (Portugal) com voz" -f $voices.Count) }
  } catch {
    Add-Result 'FAIL' 'portuguese_voice' "System.Speech indisponível: $_"
  }

  if ($Python) {
    Write-Log '--- diagnóstico Python (só leitura) ---'
    $diagArgs = @($Python.Prefix) + @('jarvis.py', 'diagnose')
    if ($Model) { $diagArgs += @('--model', $Model) }
    $d = Invoke-Native $Python.Exe $diagArgs
    foreach ($line in ($d.Output -split "`r?`n")) { if ($line) { Write-Log $line } }
    if ($d.Code -eq 0) { Add-Result 'PASS' 'jarvis_diagnose' 'pronto para validação real' }
    else { Add-Result 'WARN' 'jarvis_diagnose' "exit $($d.Code) (ver linhas FAIL acima)" }

    if (-not $SkipTests) {
      $t = Invoke-Native $Python.Exe (@($Python.Prefix) + @('-m', 'unittest', 'discover', '-s', 'tests'))
      $last = ($t.Output -split "`r?`n" | Where-Object { $_ -match '^(Ran |OK|FAILED)' }) -join ' '
      if ($t.Code -eq 0) { Add-Result 'PASS' 'unit_tests' "$last (não são testes de voz/Windows reais)" }
      else { Add-Result 'FAIL' 'unit_tests' $last; Write-Log $t.Output }
    }
  }
}

$exitCode = 0
switch ($Mode) {
  'check' {
    Write-Log 'Nenhuma instalação, aplicação ou gravação foi feita (modo check).'
  }
  'install' {
    if (-not $Python) { Write-Log 'Instala primeiro o Python (link acima).'; $exitCode = 1; break }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue) -or -not (Get-Command git -ErrorAction SilentlyContinue)) {
      Write-Log 'Instala primeiro Git e uv (links acima). Este script não instala programas do sistema.'
      $exitCode = 1; break
    }
    Write-Log 'Vai executar: python jarvis.py setup --voice  (uv sync --frozen do lockfile fixado; ~1 GB, só dentro desta pasta)'
    if (Confirm-Word 'Autorizas a instalação das dependências Python do Jarvis nesta pasta?' 'INSTALAR') {
      $exitCode = Invoke-Jarvis @('setup', '--voice')
      Write-Log "setup exit: $exitCode"
    } else { Write-Log 'Instalação cancelada pelo operador.' }
  }
  'text' {
    $a = @('voice', '--text-only', '--tts', 'none'); if ($Model) { $a += @('--model', $Model) }
    $exitCode = Invoke-Jarvis $a
  }
  'voice' {
    $a = @('voice'); if ($Model) { $a += @('--model', $Model) }
    $exitCode = Invoke-Jarvis $a
  }
  'actions' {
    Write-Log 'Modo com acções: Bloco de Notas e Calculadora. Cada pedido ainda exige responder "sim".'
    if (Confirm-Word 'Autorizas o Jarvis a abrir o Bloco de Notas e a Calculadora nesta sessão?' 'AUTORIZO') {
      $since = [DateTime]::UtcNow
      Write-Log 'AUTORIZAÇÃO: concedida pelo operador para esta sessão.'
      $a = @('voice', '--allow-actions'); if ($Model) { $a += @('--model', $Model) }
      $exitCode = Invoke-Jarvis $a
      Write-ActionAudit $since
    } else { Write-Log 'Sem autorização: nenhuma acção será possível.'; $exitCode = 1 }
  }
}

if ($Mode -eq 'text' -or $Mode -eq 'voice') { Write-Log "Sessão terminada (exit $exitCode). A conversa não é registada." }
$fails = @($Summary | Where-Object { $_.Status -eq 'FAIL' } | ForEach-Object { $_.Check })
if ($Summary.Count -gt 0) {
  if ($fails.Count -eq 0) { Write-Log 'RESUMO: sem FAIL.' } else { Write-Log ('RESUMO: FAIL em ' + ($fails -join ', ')) }
}
Write-Log "LOG: $(Protect-Text $LogFile)"
exit $exitCode
