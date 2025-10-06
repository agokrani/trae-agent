## OpenHands integration plan for perf-agents-bench

### Context
- Based on `OPENHANDS_RUN_REPORT_8aa1485f.md` and `OPENHANDS_AGENT_ANALYSIS_16_Sept_25.md` plus a review of `perf-agents-bench/`.
- Local runtime path confusion is fixed (prompts now use the actual git worktree path). CodeActAgent still loops or makes few edits; strict targets can be tripped by timing scripts like `test_opt.py`.

### Current pipeline (brief)
- Plan: resolve (human, pre) pairs into `state/plan.json`.
- Prepare: create worktree at pre, write directive `task.txt`, run OpenHands headless, collect logs/artifacts, enforce targets.
- Report: aggregate `state/runs/<run_id>/*/journal.json`.

### Key issues
- Action bias: CodeActAgent tends to analyze/loop in headless mode.
- Strict target enforcement vs timing script: extra `test_opt.py` causes enforcement FAIL despite correct target edits.
- Two invocation paths exist (simple CLI vs richer Python API path) causing drift.
- Local runtime is default; containerized mode is safer for reproducibility.

## Integration strategy

### 1) Unify agent invocation
- Prefer the Python API route already wired in `bench/prepare.py` (headless, env shaping, directive messaging).
- Gate or deprecate the parallel lightweight CLI wrapper to avoid config drift.

### 2) Normalize workspace mapping
- Local runtime: always reference the absolute worktree path in prompts/flags (kept).
- Container runtime: if used, map worktree to `/workspace` and avoid mixing path conventions.

### 3) Reconcile strict target enforcement with timing script
- Implemented: Whitelist a single scratch path `<worktree>/.bench_scratch/` and exempt it from enforcement and diffs. Prompts now force timing scripts into this directory only.

### 4) Keep prompts directive and minimal
- Retain action-focused headless directives (edit by iteration N; commit by iteration M; finish).
- Add one explicit line: “Only create timing scripts in the scratch path; do not add new files elsewhere.”

### 5) Observability and triage
- Parse/store iteration counts and first-edit timestamps from OpenHands output into `journal.json`.
- Early-flag “no edits” runs and reduce wasted iterations.

### 6) Default to containerized runs for non-local testing
- Use `bench.yaml` with container images, resource limits, `SANDBOX_USER_ID`, `.openhands` mount, and `SANDBOX_VOLUMES`.
- Keep `bench_test.yaml` for quick local development.

### 7) Consider alternative agents/models
- Trial a more action-biased agent or model configuration.
- Optionally A/B integrate `Trae Agent` behind the same agent interface for comparison on identical tasks.

### 8) Preserve GSO artifact compatibility
- Continue writing `prediction.jsonl` with `instance_id`, `model_patch` unified diff vs base, and `model_name_or_path`.

### 9) Scale and cost controls
- Keep `iterations`, `timeout`, and `max_budget_per_task` centrally configurable; enforce ceilings.
- Gate concurrency with `--max-workers` to avoid rate limits; provide a pre-flight `doctor`/smoke.

### 10) Immediate validation path
- Re-run the “chunked local attention” task (commit `8aa1485f…`) after implementing the scratch-file allowance. Expect FINISHED + PASS.
- Then expand to “prefix caching” and “moe align” tasks.

## Execution checklist (changes scoped to perf-agents-bench)
- `bench/prepare.py`
  - Added agent selection keyed by `agents.default` (supports `openhands` and `trae`).
  - For OpenHands: retained local runtime, headless directive, and volume mapping.
  - For Trae: invoke `python -m trae_agent.cli run` with `--working-dir`, `--must-patch`, `--patch-path`, `--trajectory-file`.
  - Implemented `.bench_scratch/` timing script policy in prompts; excluded from enforcement and from generated diffs/predictions.
  - Kept absolute worktree paths in all prompts (no `/workspace` normalization in local mode).
- `bench_test.yaml`
  - Switched `agents.default` to `"trae"` for local testing.
  - Added `agents.trae` block with CLI, `max_steps`, and absolute `config_file` path.
- `third-party/trae-agent/trae_config.yaml`
  - Aligned provider/model with `config/main_openai.toml` (OpenAI, `gpt-5-2025-08-07`).
  - Increased `max_tokens` to 32000 (as per current workspace change).
- Dependencies
  - Installed Trae Agent in `bench-env` using `uv pip install -e third-party/trae-agent`.
  - Pinned and installed `tree-sitter==0.24.0` and `tree-sitter-languages==1.10.2` via `uv pip` to satisfy Trae CKG dependency.
  - Policy: use `uv pip install` inside `bench-env` for all installs.

## Risks
- Agent still may make zero/off-target edits despite directives.
- Local mode regressions if `/workspace` sneaks back into prompts.
- Container image drift may affect reproducibility; pin images and cache pulls.

Additional risk observed during Trae runs:
- LLM provider API key misconfiguration will cause runs to complete without edits (401), writing empty diffs and error status.

## Success criteria
- Runs complete without path errors or loops; at least one allowed target edit per run.
- No disallowed edits except the whitelisted scratch file.
- `prediction.jsonl` and `model_patch.diff` present; strict-target enforcement PASS when enabled.

## Next actions
- Ensure valid provider credentials are available to the agent runtime (e.g., `OPENAI_API_KEY` in `.env` or environment) and rerun “chunked local attention”.
- Consider containerizing Trae runs for stricter isolation when scaling.
- Optionally trial more action-biased settings/agents; add tighter test scripts to drive edits.

---

## What we started with
- OpenHands headless integration working locally but prone to analysis loops and path confusion in historical runs.
- Strict-target enforcement flagged timing helpers like `test_opt.py` as disallowed edits.
- Two agent invocation paths existed; duplication risk.

## What we changed/fixed
- Resolved pathing: prompts consistently use the absolute worktree path in local runtime.
- Introduced `.bench_scratch/` timing policy and excluded it from enforcement and diffs.
- Unified agent selection via config; added first-class Trae Agent path in `prepare.py`.
- Switched local test config to run Trae by default; kept OpenHands path intact.
- Aligned Trae model config with `main_openai.toml` and increased `max_tokens` to 32000.
- Installed Trae and `tree-sitter` deps via `uv pip` in `bench-env`; verified imports.
- Added richer logging artifacts from Trae (`trajectory.json`) while preserving journals and predictions.

## What problems we hit during reruns
- Initial Trae run failed with `ModuleNotFoundError: tree_sitter_languages` (fixed by installing pinned `tree-sitter` packages via `uv pip`).
- Subsequent Trae run hit `401 invalid_api_key` from OpenAI → no edits, empty diff, run marked error despite successful execution path.
- After dependency fixes, Trae executed and logged successfully, but still produced no edits because of the API key error (empty patch).

## What still remains
- Provide valid provider credentials (e.g., `OPENAI_API_KEY`) to enable the LLM to act; rerun to validate edits land within targets.
- Optionally test alternative agents/models or increase action bias if edits remain sparse.
- Consider default containerization for Trae at scale to standardize the runtime and further isolate side effects.
