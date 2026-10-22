"""MANUAL script - runs one real LLM extraction on a local PDF.

This script is **not** part of the test suite. It calls a real provider and
therefore costs money. It is only meant to be run by hand:

.. code-block:: bash

    cd backend
    .venv/bin/python -m extraction.llm.manual.run_manual ../contracts/fixtures/pdfs/synthetic_mosfet.pdf

The provider key is read from the ``.env`` file of the repository root (never
committed, see ``.env.example``).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

from extraction.llm import CallRecorder, LLMExtractorImpl  # noqa: E402
from shared.config import get_settings  # noqa: E402
from shared.schemas import Family  # noqa: E402

#: The environment variable that holds the key of each supported provider.
PROVIDER_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google_genai": "GOOGLE_API_KEY",
    "google_vertexai": "GOOGLE_APPLICATION_CREDENTIALS",
    "groq": "GROQ_API_KEY",
    "mistralai": "MISTRAL_API_KEY",
    "xai": "XAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "together": "TOGETHER_API_KEY",
}

PAGE_KEYWORDS = (
    "electrical characteristics",
    "absolute maximum ratings",
    "electrical characteristics",
)


def load_env() -> None:
    """Load the ``.env`` file of the repository root into the environment."""
    for candidate in (REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"):
        if candidate.exists():
            load_dotenv(candidate, override=False)


def check_key(provider: str) -> bool:
    """Return ``True`` when the key of the provider is available.

    A provider that runs locally (for example ``ollama``) needs no key.
    """
    variable = PROVIDER_KEY_ENV.get(provider)
    if variable is None:
        print(
            f"! no known key variable for the provider {provider!r} - "
            "the provider must find its own credentials",
            file=sys.stderr,
        )
        return True
    if not os.getenv(variable):
        print(
            f"! {variable} is not set - add it to {REPO_ROOT / '.env'} before running",
            file=sys.stderr,
        )
        return False
    return True


def page_texts(pdf_path: Path) -> list[tuple[int, str]]:
    """Return the text of the pages that hold a characteristics table."""
    import pymupdf

    selected: list[tuple[int, str]] = []
    with pymupdf.open(pdf_path) as document:
        for index, page in enumerate(document, start=1):
            text = page.get_text() or ""
            if any(keyword in text.lower() for keyword in PAGE_KEYWORDS):
                selected.append((index, text))
        if not selected:
            selected = [
                (index, page.get_text() or "") for index, page in enumerate(document, start=1)
            ]
    return selected


def main(argv: list[str] | None = None) -> int:
    """Run one real extraction and print the result and the cost."""
    parser = argparse.ArgumentParser(description="Manual PartPilot LLM extraction")
    parser.add_argument("pdf", help="path of the local PDF")
    parser.add_argument(
        "--family",
        default="mosfet",
        choices=["mosfet", "gate_driver"],
        help="the component family",
    )
    parser.add_argument("--part-id", default=None, help="optional part id")
    args = parser.parse_args(argv)

    load_env()
    settings = get_settings()
    if not check_key(settings.llm_provider):
        return 3

    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.exists():
        print(f"! {pdf_path} does not exist", file=sys.stderr)
        return 2

    pages = page_texts(pdf_path)
    print(f"pages with a characteristics table: {[number for number, _ in pages]}")

    recorder = CallRecorder(settings=settings)
    extractor = LLMExtractorImpl(recorder=recorder, settings=settings)
    result = extractor.extract_tier2(pages, Family(args.family), part_id=args.part_id)

    print("\n--- values -------------------------------------------------")
    for value in result.values:
        print(
            f"{value.name:28s} {value.value!r:>12} {value.unit or '':<8} "
            f"page={value.page} conf={value.confidence:.2f} method={value.method}"
        )
        if value.condition:
            print(f"{'':28s} condition: {value.condition}")
        if value.raw_text:
            print(f"{'':28s} raw: {value.raw_text[:110]}")
    print("\n--- failed fields -----------------------------------------")
    print(", ".join(result.failed_fields) or "(none)")
    print("\n--- calls ---------------------------------------------------")
    for record in recorder.records:
        print(
            f"{record.chain:24s} model={record.model} "
            f"in={record.tokens_in} out={record.tokens_out} "
            f"cost=${record.cost:.6f} cached={record.cached} "
            f"prompt={record.prompt_version} {record.duration_ms}ms"
        )
    print(f"\ntotal cost: ${recorder.total_cost:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
