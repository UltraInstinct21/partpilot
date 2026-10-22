# HANDOFF - agent C-llm (plan WP4: tier 2 and tier 3, LangChain)

Branch: `agent/c-llm`
Folder: `backend/extraction/llm/**` and `backend/tests/llm/**`

## What exists

| file | purpose |
| --- | --- |
| `extraction/llm/factory.py` | builds the chat model (`init_chat_model`), the rate limiter, the retry wrapper and the SQLite cache |
| `extraction/llm/prompt_store.py` | loads the prompt files, reads their version and chain header |
| `extraction/llm/prompts/*.txt` | the five prompts, one file per chain, version in the file name |
| `extraction/llm/parameters.py` | the allow-list of standard parameter names (derived from `shared.schemas`) and the unit hints |
| `extraction/llm/chains.py` | the five chains, the prompt payloads and the result handling |
| `extraction/llm/recorder.py` | `CallRecorder`, `NoOpRecorder`, cost estimation and the usage metadata reader |
| `extraction/llm/extractor.py` | `LLMExtractorImpl` - the implementation of the `LLMExtractor` protocol |
| `extraction/llm/manual/run_manual.py` | manual script for one real extraction (never collected by pytest) |
| `tests/llm/**` | 87 tests, fake chat model only, no network |

## Public API

```python
from extraction.llm import LLMExtractorImpl, CallRecorder, build_chat_model
from shared.schemas import Family

recorder = CallRecorder()                     # keeps the calls in memory
extractor = LLMExtractorImpl(recorder=recorder)

result = extractor.extract_tier2([(3, page_text)], Family.MOSFET, part_id="p1")
result = extractor.extract_tier3([(4, png_bytes)], Family.GATE_DRIVER, part_id="p1")
name = extractor.map_name("RDS(on)", Family.MOSFET)          # str | None (a person approves)
filt = extractor.build_search_filter("infineon mosfet rds on below 50 mOhm")
sentence = extractor.explain_alternative({"rds_on": {"a": 45.0, "b": 25.0}}, "IRFP260N")
```

`LLMExtractorImpl` implements `shared.interfaces.LLMExtractor` exactly:

```python
extract_tier2(pages: Iterable[tuple[int, str]], family, part_id=None) -> ExtractionResult
extract_tier3(page_images: Iterable[tuple[int, bytes]], family, part_id=None) -> ExtractionResult
map_name(raw_name: str, family) -> str | None
build_search_filter(query: str) -> SearchFilter
explain_alternative(differences: dict[str, dict[str, float | None]], mpn: str) -> str
```

Constructor: `LLMExtractorImpl(model=None, recorder=None, settings=None,
prompts_dir=None, vision_model=None)`.

* `model` - an already built chat model. When it is given, it is used for the
  text chain **and** for the vision chain (that is how the tests avoid a real
  provider). When it is `None`, the model is built lazily on the first call -
  never at import time.
* `recorder` - any object with `record(record: LLMCallRecord) -> None`. Without
  one, a no-op recorder is used. `CallRecorder(repository=...)` forwards every
  call to `PartsRepository.record_llm_call` as soon as the repository exists.

Other helpers:

```python
build_chat_model(settings=None, vision=False, model=None, **kwargs) -> Runnable
setup_llm_cache(settings=None, force=False) -> bool          # SQLiteCache
chat_model_core(model) -> BaseChatModel | None               # unwraps RunnableRetry
load_prompt(name, version=None, directory=None) -> str
prompt_version(name, version=None, directory=None) -> str    # "v1"
prompt_chain(name, version=None, directory=None) -> str
estimate_cost(tokens_in, tokens_out, settings=None) -> float
build_call_record(...) -> LLMCallRecord
```

## How to run

```bash
cd backend
.venv/bin/python -m pytest -q          # all tests
.venv/bin/python -m ruff check .
.venv/bin/python -m black --check .
```

Manual run (costs money, reads the key from the repository `.env`):

```bash
cd backend
.venv/bin/python -m extraction.llm.manual.run_manual \
    ../contracts/fixtures/pdfs/synthetic_mosfet.pdf --family mosfet
```

It prints the extracted values, the failed fields, every call (chain, model,
tokens, cost, prompt version, duration) and the total cost. It exits with
code 3 when the provider key is missing.

## Prompt versions

| chain | file | version |
| --- | --- | --- |
| `tier2_extractor` | `prompts/tier2_extractor_v1.txt` | `v1` |
| `tier3_vision` | `prompts/tier3_vision_v1.txt` | `v1` |
| `name_mapper` | `prompts/name_mapper_v1.txt` | `v1` |
| `search_filter` | `prompts/search_filter_v1.txt` | `v1` |
| `alternative_explainer` | `prompts/alternative_explainer_v1.txt` | `v1` |

Every file starts with `# version: v1` and `# chain: <name>`. The version is
written to `llm_calls.prompt_version`. To change a prompt: copy the file to
`<name>_v2.txt`, edit it, and the loader picks the highest version. The old
version stays in the repository, so a stored result can always be explained.

## How NFR-03 ("the LLM never invents a value") is enforced

1. The prompt forbids guessing and asks for `null` when the value is not in
   the text.
2. A field the model leaves empty becomes a **failed field**
   (`ExtractionResult.failed_fields`). It is never filled with a default, a
   typical value or a range.
3. The search filter drops every constraint on a parameter name outside the
   allow-list (and logs it).
4. The name mapper returns `None` when the model is unsure
   (`confidence < 0.5`), when it proposes `null` or when it proposes a name
   that does not exist for the family.
5. The alternative explainer is rejected when it is longer than 25 words or
   when it contains a number that is not in its input; a deterministic sentence
   is used instead.

## Assumptions about the frozen contracts

* The slot names of `MosfetSpec` / `GateDriverSpec` are the standard parameter
  names. `extraction/llm/parameters.py` derives the allow-list from them, so
  the allow-list can never drift away from `shared/schemas.py`.
* `SpecValue` has a single numeric `value` (no min/typ/max). The extractor
  therefore fills `ParameterValue.value` only; the min/typ/max split stays
  with tier 1 and the validator (WP5).
* `MosfetSpec.package` and `GateDriverSpec.package` are `SpecValue` slots, but
  a package is a name and not a number. The model cannot fill a number for
  them, so they always end up in `failed_fields`. **Known gap**, see below.
* `ParameterValue.condition` is a free `dict[str, Any]`; the model returns the
  test condition as text (`{"vgs": "10 V", "id": "10 A"}`).
* The unit is reported **as printed** in the datasheet (e.g. `mOhm`), the
  validator converts it to the canonical unit (WP5).
* `SearchFilter` has no field for a warning, so a dropped constraint is only
  logged (`logger.warning("dropping filter constraint on unknown parameter")`).

## Known gaps / not done

* **The package is not installable as a wheel yet.** The prompt files are
  found relative to the module, which works from the source tree but needs
  `[tool.setuptools.package-data]` in the frozen `backend/pyproject.toml`.
  Change request: `docs/CHANGE_REQUESTS/c-llm-1.md`.
* **No accuracy measurement on the gold set** (plan WP4 acceptance test). The
  chain has to be run over the gold set with a real key; the manual script is
  the starting point. The cost per datasheet is printed by the manual script
  and stored in `llm_calls`.
* **Tier 3 compares nothing with tier 2.** The plan asks for a difference
  between the tier 2 and the tier 3 result to be marked for review; the
  comparison needs the two results in one place and belongs to the job
  runner (WP6).
* **The SQLite cache is global** (`set_llm_cache`). A cache hit of the
  provider cache is *not* reported as `cached=True` in the call record,
  because LangChain does not mark the cached message. `cached=True` is
  reported for the per-chain result cache of the extractor (the second call
  with the same input).
* **The vision chain sends one call per page.** A page that holds no
  parameter still costs one call.
* The prompt files are not translated and the chains do not speak German.
* No retry/back-off on the *extractor* level: the retry comes from the
  LangChain `RunnableRetry` wrapper of the factory.

## Chain summary

| chain | model call | structured target |
| --- | --- | --- |
| `tier2_extractor` | one call with all given pages | `MosfetSpec` / `GateDriverSpec` |
| `tier3_vision` | one call per page image | `MosfetSpec` / `GateDriverSpec` |
| `name_mapper` | one call | `NameMappingProposal` (local model) |
| `search_filter` | one call | `SearchFilter` (frozen) |
| `alternative_explainer` | one call, plain text | one sentence |

`with_structured_output(..., include_raw=True)` is used everywhere, so the raw
message (and with it the token usage) is available for the cost accounting.
