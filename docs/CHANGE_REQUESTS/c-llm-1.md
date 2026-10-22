# Change request CR-1 (agent C-llm): package the prompt files and the manual script

**From:** agent `c-llm` (WP4, LLM extraction)
**To:** the orchestrator (owner of `backend/pyproject.toml`)
**Reason:** the LLM package ships data files and a sub package that the frozen
`pyproject.toml` does not know about.

## What is needed

1. `backend/pyproject.toml` -> `[tool.setuptools] packages` must also contain
   `"extraction.llm.manual"` (the manual script lives in
   `backend/extraction/llm/manual/`).
2. `backend/pyproject.toml` needs package data so the prompt files survive a
   wheel build:

   ```toml
   [tool.setuptools.package-data]
   "extraction.llm" = ["prompts/*.txt"]
   ```

   Without it, `extraction.llm.prompt_store.load_prompt()` only finds the
   prompt files when the backend runs from the source tree.

## Why it matters

`load_prompt(name, version)` resolves the prompt files relative to the module
(`backend/extraction/llm/prompts/<name>_v<version>.txt`). In an installed
wheel the directory would be empty and every chain would fail with
`PromptNotFoundError`.

## Current behaviour (no change needed for the source tree)

The backend is used from the source tree (`backend/.venv`, `pythonpath = ["."]`
in pytest), so the prompt files are found today and all tests pass. This
request only makes the package installable.

## Note

The prompt version is stored with every call (`llm_calls.prompt_version`), so
adding a new prompt version never invalidates a stored result silently.
