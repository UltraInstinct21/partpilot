"""The matplotlib charts of the evaluation (plan WP8, plan section 15).

The charts turn the JSON file of one evaluation run into PNG files. The
charts are the ones that the report uses:

* the field accuracy per tier;
* the cost per tier;
* the field accuracy per manufacturer;
* the confusion matrix of the validation experiment;
* the cost against the accuracy.

The module uses the non interactive ``Agg`` backend, so it works on a server
without a display. ``matplotlib`` is an optional dependency: when it is
missing the functions raise :class:`ChartsUnavailable` with a clear message
instead of failing with an import error.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

__all__ = [
    "CHARTS",
    "ChartsUnavailable",
    "accuracy_by_manufacturer_chart",
    "accuracy_by_tier_chart",
    "confusion_matrix_chart",
    "cost_by_tier_chart",
    "cost_vs_accuracy_chart",
    "load_results",
    "render_all",
]

#: The name of every chart that :func:`render_all` writes.
CHARTS: tuple[str, ...] = (
    "accuracy_by_tier",
    "cost_by_tier",
    "accuracy_by_manufacturer",
    "validation_confusion",
    "cost_vs_accuracy",
)

#: The directory that holds the charts. It is inside the repository.
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "results"


class ChartsUnavailable(RuntimeError):
    """Raised when the charts cannot be written, for example no matplotlib."""


def _pyplot() -> Any:
    """Return the ``matplotlib.pyplot`` module with the Agg backend."""
    try:
        import matplotlib
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ChartsUnavailable(
            "matplotlib is not installed. Install it with "
            "`backend/.venv/bin/python -m pip install matplotlib`."
        ) from exc
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def load_results(path: str | Path) -> dict[str, Any]:
    """Read the JSON file of one evaluation run."""
    file_path = Path(path)
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"the results file {file_path} must hold a JSON object")
    return payload


def _tiers(results: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    tiers = results.get("tiers") or {}
    if not isinstance(tiers, Mapping):
        return {}
    return {
        str(name): dict(value) if isinstance(value, Mapping) else {"accuracy": float(value)}
        for name, value in tiers.items()
    }


def _manufacturers(results: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    data = results.get("manufacturers") or {}
    if not isinstance(data, Mapping):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for name, value in data.items():
        if isinstance(value, Mapping):
            out[str(name)] = dict(value)
        else:
            out[str(name)] = {"accuracy": float(value)}
    return out


def _save(plt: Any, figure: Any, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)
    return path


def accuracy_by_tier_chart(
    results: Mapping[str, Any], output_dir: str | Path | None = None
) -> Path:
    """Write the bar chart of the field accuracy per tier."""
    plt = _pyplot()
    tiers = _tiers(results)
    if not tiers:
        raise ChartsUnavailable("the results file holds no tier data")
    names = list(tiers)
    values = [float(tiers[name].get("accuracy", 0.0)) * 100.0 for name in names]
    figure, axes = plt.subplots(figsize=(7, 4))
    bars = axes.bar(names, values, color="#3b82f6")
    axes.set_ylabel("field accuracy (%)")
    axes.set_title("Field accuracy per extraction tier")
    axes.set_ylim(0, 100)
    axes.bar_label(bars, fmt="%.1f %%", padding=2)
    directory = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    return _save(plt, figure, directory / "accuracy_by_tier.png")


def cost_by_tier_chart(results: Mapping[str, Any], output_dir: str | Path | None = None) -> Path:
    """Write the bar chart of the cost per tier."""
    plt = _pyplot()
    tiers = _tiers(results)
    if not tiers:
        raise ChartsUnavailable("the results file holds no tier data")
    names = list(tiers)
    values = [float(tiers[name].get("cost", 0.0)) for name in names]
    figure, axes = plt.subplots(figsize=(7, 4))
    bars = axes.bar(names, values, color="#f59e0b")
    axes.set_ylabel("cost (USD)")
    axes.set_title("LLM cost per extraction tier")
    axes.bar_label(bars, fmt="%.4f", padding=2)
    directory = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    return _save(plt, figure, directory / "cost_by_tier.png")


def accuracy_by_manufacturer_chart(
    results: Mapping[str, Any], output_dir: str | Path | None = None
) -> Path:
    """Write the horizontal bar chart of the accuracy per manufacturer."""
    plt = _pyplot()
    manufacturers = _manufacturers(results)
    if not manufacturers:
        raise ChartsUnavailable("the results file holds no manufacturer data")
    ordered = sorted(manufacturers.items(), key=lambda item: item[1].get("accuracy", 0.0))
    names = [name for name, _ in ordered]
    values = [float(data.get("accuracy", 0.0)) * 100.0 for _, data in ordered]
    figure, axes = plt.subplots(figsize=(7, max(3, 0.5 * len(names) + 1)))
    bars = axes.barh(names, values, color="#10b981")
    axes.set_xlabel("field accuracy (%)")
    axes.set_title("Field accuracy per manufacturer")
    axes.set_xlim(0, 100)
    axes.bar_label(bars, fmt="%.1f %%", padding=2)
    directory = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    return _save(plt, figure, directory / "accuracy_by_manufacturer.png")


def confusion_matrix_chart(
    results: Mapping[str, Any], output_dir: str | Path | None = None
) -> Path:
    """Write the heat map of the confusion matrix of the validation experiment."""
    plt = _pyplot()
    confusion = results.get("confusion") or {}
    if not isinstance(confusion, Mapping) or not confusion.get("matrix"):
        raise ChartsUnavailable("the results file holds no confusion matrix")
    labels = [str(label) for label in confusion.get("labels", [])]
    matrix = confusion["matrix"]
    figure, axes = plt.subplots(figsize=(5, 4.5))
    image = axes.imshow(matrix, cmap="Blues")
    axes.set_xticks(range(len(labels)), labels)
    axes.set_yticks(range(len(labels)), labels)
    axes.set_xlabel("predicted label")
    axes.set_ylabel("true label")
    axes.set_title("Validation: wrong values stopped")
    for row, line in enumerate(matrix):
        for column, value in enumerate(line):
            axes.text(
                column,
                row,
                str(value),
                ha="center",
                va="center",
                color="white" if value and value > max(max(row) for row in matrix) / 2 else "black",
            )
    figure.colorbar(image, ax=axes)
    directory = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    return _save(plt, figure, directory / "validation_confusion.png")


def cost_vs_accuracy_chart(
    results: Mapping[str, Any], output_dir: str | Path | None = None
) -> Path:
    """Write the scatter chart of the cost against the accuracy."""
    plt = _pyplot()
    points: Sequence[Mapping[str, Any]] = results.get("cost_vs_accuracy") or []
    if not points:
        tiers = _tiers(results)
        points = [
            {
                "name": name,
                "cost": float(data.get("cost", 0.0)),
                "accuracy": float(data.get("accuracy", 0.0)),
            }
            for name, data in tiers.items()
        ]
    if not points:
        raise ChartsUnavailable("the results file holds no cost and accuracy data")
    figure, axes = plt.subplots(figsize=(6.5, 4.5))
    for point in points:
        axes.scatter(
            float(point.get("cost", 0.0)),
            float(point.get("accuracy", 0.0)) * 100.0,
            s=70,
        )
        axes.annotate(
            str(point.get("name", "")),
            (float(point.get("cost", 0.0)), float(point.get("accuracy", 0.0)) * 100.0),
            textcoords="offset points",
            xytext=(6, 4),
        )
    axes.set_xlabel("cost (USD)")
    axes.set_ylabel("field accuracy (%)")
    axes.set_title("Cost against accuracy")
    axes.grid(True, linestyle=":", alpha=0.6)
    directory = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    return _save(plt, figure, directory / "cost_vs_accuracy.png")


def render_all(results: Mapping[str, Any], output_dir: str | Path | None = None) -> list[Path]:
    """Write every chart and return the list of the written files."""
    written: list[Path] = []
    for chart in (
        accuracy_by_tier_chart,
        cost_by_tier_chart,
        accuracy_by_manufacturer_chart,
        confusion_matrix_chart,
        cost_vs_accuracy_chart,
    ):
        try:
            written.append(chart(results, output_dir))
        except ChartsUnavailable:
            continue
    return written
