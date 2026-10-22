# Handoff: evaluation, CI, Docker and documents

**Agent:** i-eval-docs
**Branch:** `agent/i-eval-docs`
**Plan:** WP8 (evaluation), WP9 (documents and demo), section 12 (ethics),
section 14 (quality checks), section 15 (the mapping to the evaluation
scheme).

---

## 1. What I delivered

### The evaluation harness (`eval/`)

| File | Content |
| --- | --- |
| `eval/metrics.py` | The pure metric functions: `field_accuracy`, `precision_at_k`, `recall`, `mrr`, `refusal_rate`, `cost_per_datasheet`, `latency_stats`, `confusion`, `normalise_value`, `values_match`, `accuracy_by_manufacturer`, `accuracy_by_field`. |
| `eval/gold_set.py` | `validate_gold_set`, `load_gold_set`, `inter_annotator_agreement`, `agreement_rate`, the `GoldRow` model and the column list. |
| `eval/runners.py` | The six experiments of WP8: `experiment_1_tiers`, `experiment_2_tiered_vs_best`, `experiment_3_validation_on_off`, `experiment_4_search`, `experiment_5_alternatives`, `experiment_6_by_manufacturer`. Each one takes the implementation through injection. |
| `eval/queries.py` | The 30 natural-language search queries with the expected filter, and the validator of the list. |
| `eval/charts.py` | The five charts with the non interactive `Agg` backend. |
| `eval/demo.py` | The fake extractor, validator, filter builder and alternative finder, and the demo run. No network, no key. |
| `eval/__main__.py` | The command line: `validate-gold`, `agreement`, `queries`, `charts`, `demo`. |
| `eval/gold_set_template.csv` | The format of the gold set with three example rows. |
| `eval/README.md` | How to run the harness, how to add a gold set, what each experiment measures. |
| `eval/tests/` | 102 tests. |

The harness imports nothing from another agent's package. It works with any
object that satisfies the protocols of `backend/shared/interfaces.py`, or
with the plain dictionaries and the small dataclasses that the tests use.

### The documents (`docs/`)

| File | Content |
| --- | --- |
| `docs/ETHICS.md` | The one page ethics note of plan section 12, with the documented limits of DigiKey (120/min, 1000/day), Mouser (30/min, 1000/day), Nexar (1000 parts/month) and the 1 s download delay. |
| `docs/REPORT.md` | The skeleton of the report of 8 to 10 pages: ten sections, the headings, a note of what to write and the place of every table and chart. |
| `docs/DEMO.md` | The demo script of the six steps, the test data, the backup recording plan and the checklist of the day before. |
| `docs/GOLD_SET.md` | How to build the gold set of 80 parts, the fields, the second check of 20 % and the commands of the validator. |
| `docs/demo_bom.csv` | The BOM file of the demo (six lines, one of them wrong on purpose). |
| `docs/HANDOFF.md` | This file. |
| `docs/CHANGE_REQUESTS/i-eval-docs-1.md` | The request to add `matplotlib` to `backend/pyproject.toml`. |

### The CI (`.github/workflows/`)

* `ci.yml`: a backend job (python 3.12, `uv sync`, ruff, black, pytest on
  the backend and on the evaluation package) and a frontend job (node 22,
  `npm ci`, eslint, prettier, `tsc -b`, vitest). No secret is needed.
* `secret-scan.yml`: greps the repository for `sk-`, `api_key=`,
  `client_secret`, the private key headers, the slack and the github
  tokens. The environment template (`.env.example`) and the folder `docs/`
  are excluded. The job also fails when a `.env` file or a PDF is tracked.

### The Docker files (`docker/` and `docker-compose.yml`)

* `docker/Dockerfile.backend`: a slim python 3.12 image with `uv`, the
  backend installed with `uv sync --frozen`, a non root user and the
  command `uvicorn app.main:app`.
* `docker/Dockerfile.frontend`: a node build stage and an nginx serve stage.
* `docker/nginx.conf`: the SPA fallback and the proxy of `/api` to the
  backend.
* `docker-compose.yml`: the service `api` (port 8000), the service `web`
  (port 5173) and the service `mock-api` (profile `mock`, port 8001). The
  folder `data/` is a volume. No secret is in an image: the keys come from
  the `.env` file of the server.
* `.dockerignore` at the root: keeps the secrets, the virtual environments
  and the raw data out of the build context.

### The README (`README.md`)

What PartPilot is, the architecture diagram (Mermaid), the folder layout,
one documented command per service, the keys and where to put them, the map
from FR-01 to FR-15 and NFR-01 to NFR-07 to the module that covers it, the
six steps of the demo and the known gaps.

## 2. How to run it

```bash
# the tests of the harness
cd backend && .venv/bin/python -m pytest ../eval -q

# the lint of the harness
cd backend
.venv/bin/python -m ruff check --config pyproject.toml ../eval
.venv/bin/python -m black --check --config pyproject.toml ../eval

# the demo of the six experiments, with the charts
cd backend && .venv/bin/python -m eval demo

# the gold set
cd backend && .venv/bin/python -m eval validate-gold ../eval/gold_set.csv
cd backend && .venv/bin/python -m eval agreement ../eval/gold_set.csv
```

The result files and the charts are written in `eval/results/`. They are not
in Git (`eval/results/.gitignore`).

## 3. The state of the tests

```
eval/tests/test_metrics.py    39 tests
eval/tests/test_gold_set.py   17 tests
eval/tests/test_runners.py    19 tests
eval/tests/test_charts.py     10 tests
eval/tests/test_queries.py     8 tests
eval/tests/test_cli.py         9 tests
------------------------------
total                        102 tests
```

All 102 pass. `ruff` and `black` are clean on `eval/` and on `backend/`.

The chart tests use `pytest.importorskip("matplotlib")`. They are skipped
and not failed when the package is missing.

## 4. The known gaps

| Gap | Why | What is needed |
| --- | --- | --- |
| `matplotlib` is not in `backend/pyproject.toml`. | I may not edit that file. | The orchestrator adds `"matplotlib>=3.9,<4"` and refreshes `uv.lock`. See `docs/CHANGE_REQUESTS/i-eval-docs-1.md`. The package was installed in the working virtual environment with `uv pip install`, so the charts run here. |
| The real gold set of 80 parts. | It needs the real datasheets and two members with the time to label them. | The method is in `docs/GOLD_SET.md`. The template is `eval/gold_set_template.csv` and the validator is `python -m eval validate-gold`. |
| The real numbers of the six experiments. | They need the real implementation of the other agents. | Write a script that builds the real implementation and calls the six runners. The demo shows the shape of such a script. The runners accept any object with the right methods. |
| The expert labels of experiment 5. | Two or three members must judge the alternatives. | A CSV or a JSON with the part and the accepted alternatives. The runner takes any mapping. |
| The Docker build. | No Docker daemon runs on this machine. | `docker compose config` is clean. The build of the images is not tested here. |
| The report and the slides. | They need the numbers of the real run. | The skeleton is `docs/REPORT.md`. |

## 5. What I did not change

I did not edit `docs/PLAN.md`, `docs/CONTRACTS.md`, `backend/shared/`,
`backend/pyproject.toml`, `backend/uv.lock`, `contracts/`, `frontend/**` or
the folder of any other agent. The only file outside my folder is the new
`.dockerignore` at the root, which the Docker build needs. It holds no
secret and no rule of the other agents.

## 6. The next steps for the team

1. The orchestrator merges `docs/CHANGE_REQUESTS/i-eval-docs-1.md` and adds
   `matplotlib` to the backend.
2. Member A and member B give the real extractor and the real validator to
   the six runners and write the real result file.
3. Member D labels the gold set with the method of `docs/GOLD_SET.md`, and
   a second member checks 20 % of the labels.
4. The report is filled with the numbers of `eval/results/` and the charts
   of `eval/results/`.
