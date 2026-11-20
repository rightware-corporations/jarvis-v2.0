# RIGHTWARE — JARVIS do Issa — K04: execução independente de Colab/Kaggle
**Investigação:** 09/11/2026. **Status:** EXTERNAL RESEARCH / RECOMMENDATION, not an approved procurement or K04 test result.

## 1. Problem and evidence
The Kaggle editor showed `Failed to Authorize Session` and an official banner acknowledging notebook startup/disconnection issues, so K04 could not run there. The operator reports that Google Colab is slow and fails to open the provided notebook. The generated `RIGHTWARE_JARVIS_K04_GOOGLE_COLAB.ipynb` was locally checked with `nbformat.validate`: syntactically/structurally valid (13 cells). This **does not** prove Colab compatibility or diagnose the UI failure. Do not re-run old K03 benchmarks or erase old artifacts in pursuit of a new platform.

**Core portability:** WORK02 is already a Python program in `labs/work02_active_agent/run_real.py` under the fixed GitHub code revision `fa9faa9256b7941f2efd5c638fe6b6b7bb6efdb5` and pinned OpenJarvis `f21d902f4d3bd7f0f3f138f1a4613019a394b549`. The runner is NOT tied to any notebook. It expects pinned source, an OpenJarvis venv, Ollama running at `127.0.0.1:11434`, `qwen3.5:4b` downloaded, and a GPU (`--allow-cpu` permits a separately marked CPU test). The benchmark uses `--n 10 --security-n 3`, ≥8/10 main PASS and zero security violations, distinct document hashes and source-matched facts, calls to real read/write/verify tools.

## 2. Provider scan (official source findings; account availability NOT verified)
| Option | Grounded offer / restrictions | Fit for K04 |
|---|---|---|
| Lightning AI Studios | Official pricing says 5 free credits on sign-up, 25 extra only after adding a card; up to ~80 GPU hours is a **maximum with credits, not unconditional free access**. Studio has terminal/SSH/Git and persistent files. Free studios restart every four hours. | **First candidate**: allocate T4 16GB or better, check actual account credit/region/GPU before setup. Never activate paid charges without consent. |
| Paperspace Gradient Notebooks / DigitalOcean | Official docs list free M4000 machine in Free Gradient plan; limited available capacity, maximum free machine session 6h; free workspace privacy depends on plan and product rules. | Backup candidate; older M4000 and capacity/driver must be tested. |
| Modal | Starter official US$30/month free compute credits; functions/containers architecture requires adapting the WORK02 entrypoint, not a drop-in notebook. | Advanced backup only. |
| Hugging Face ZeroGPU | Free account 5 min/day, built for Gradio Space GPU-decorated functions. | Not appropriate for entire WORK02 long-lived Ollama server / 13 trials without substantial redesign. |
| SageMaker Studio Lab | AWS explicitly states **closed to new users**; existing users can continue. | Exclude for new accounts. |
| Local Windows PC | No notebook provider needed; local Ollama, Python, Git and `--allow-cpu` if GPU not detected; slower, hardware/ram unknown. | Best truly provider-independent fallback if RAM/hardware adequate. Measure before assuming capacity. |
| Kaggle / Colab | Currently reported unusable; quota and interruptions can occur. | Resume after platform recovery, not primary near-term dependency. |

Official sources consulted:
- https://studio.lightning.ai/pricing/
- https://platform.lightning.ai/studio
- https://docs.digitalocean.com/products/paperspace/pricing/
- https://docs.digitalocean.com/products/paperspace/notebooks/details/features/
- https://modal.com/pricing
- https://huggingface.co/docs/hub/spaces-zerogpu
- https://docs.aws.amazon.com/sagemaker/latest/dg/studio-lab.html

## 3. Platform-independent execution strategy

**Phase A — availability only, no installation (Lightning first):** create account; inspect actual credit balance (avoid payment); create Studio with GPU T4 16GB or better if available; open terminal and run only:
```bash
nvidia-smi
python --version
git --version
```
**STOP** if no GPU or service requires a payment that operator has not approved. An empty GPU pool is a platform limitation, not Jarvis failure.

**Phase B — bootstrap in approved Linux GPU host:** clone public `jarvis-v2.0`, explicitly checkout the immutable WORK02 SHA, initialize the pinned submodule, prepare an isolated venv using the existing `uv`/lockfile, install/launch Ollama at loopback with Qwen3.5 4B; avoid arbitrary cloud credentials. Do not blindly use `curl | sh` without validating official download/source and necessary privileges. Retain exact software versions/digests when possible.

**Phase C — run unchanged WORK02 code via terminal**:
```bash
cd jarvis-v2.0
vendor/openjarvis/.venv/bin/python labs/work02_active_agent/run_real.py \
  --expect-sha fa9faa9256b7941f2efd5c638fe6b6b7bb6efdb5 \
  --n 10 --security-n 3
```
Outputs `labs/work02_active_agent/evidence/real-*.zip` and `summary.json`. Preserve outputs outside ephemeral VM (secure download or authorized Drive). Never call this QWEN REAL PASS based on FAKE results or CI alone. Never use `main` or overwrite input source docs.

**Phase D — actual Issa PC:** after K04 proof, get CPU/RAM/GPU/VRAM/Windows version and test local inference and intended automation; cloud GPU benchmarks do not establish viability on the destination machine.

## 4. Decision/status
**RECOMMENDATION:** run K04 in Lightning AI GPU Studio via terminal (no notebook conversion); fallback Paperspace, then CPU local. Keep Kaggle and Colab artifacts. No account resources created, GPU allocated, models downloaded, benchmark executed or payment authorized by this document.
