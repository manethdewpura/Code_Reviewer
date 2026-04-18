# MAS Code Reviewer (Offline Multi-Agent System)

Locally running **Multi-Agent Code Review & Refactoring System** that analyzes a target source folder and generates a **structured JSON report**.

## What this demonstrates (CTSE Assignment 2 requirements)

- **Multi-agent orchestration**: 4 distinct agents coordinated via **LangGraph** (Coordinator → Quality/Security/Refactor → Report).
- **Tool usage**: agents call custom Python tools to read files, compute complexity, and scan security patterns.
- **State management**: a single shared `ReviewState` object is passed between graph nodes.
- **Observability**: JSONL tracing of agent inputs/outputs/tool results under `runs/`.
- **Zero-cost + local**: uses **Ollama** only (no paid APIs).

## Setup

1) Install and run Ollama, then pull a model:

```bash
ollama pull llama3.1:8b
```

2) Create a virtualenv and install dependencies:

```bash
cd MAS-Code-Reviewer
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
```

## Run

Analyze a project folder and write a JSON report:

```bash
python main.py --project "C:\\path\\to\\your\\project" --model "llama3.1:8b" --out report.json
```

You can also run with a smaller model (if available locally), e.g. `phi3`.

## Frontend (Streamlit)

Run a local web UI to analyze a project, inspect findings, and download the generated report:

```bash
streamlit run frontend/app.py
```

In the UI:
- Enter the target project path.
- Select a local Ollama model.
- Click **Run Analysis**.
- View summary + findings and download the JSON report.

## Tests / Evaluation

### Deterministic unit + integration tests (default)

```bash
pytest -q
```

### Property-style tool evaluation (included in `pytest`)

The suite includes randomized “property-style” checks for the custom tools (without adding extra dependencies like Hypothesis). These run automatically as part of `pytest`.

### Optional: local “LLM-as-a-judge” evaluation (Ollama only)

This is **skipped by default** to keep tests deterministic and to avoid requiring a running Ollama daemon.

- Run as a script:

```bash
python evaluation/run_llm_judge.py --project "C:\\path\\to\\your\\project" --model "llama3.1:8b" --out judge_result.json
```

- Or enable the optional pytest-based judge:

```bash
set OLLAMA_EVAL=1
pytest -q
```

## Output

- **Report (JSON)**: written under `reports/` by default (when `--out` is a bare filename).
- **Run trace (JSONL)**: stored in `runs/` with agent I/O and tool call outputs.

