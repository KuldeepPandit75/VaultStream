"""READ-ONLY inspection of the raw pickles.

Writes nothing. Prints the true shape/dtype/null profile plus samples of the
nested columns so the schema in Task 3 is built against reality rather than an
assumed Kaggle layout.

Usage:
    python -m etl.inspect_data
    python -m etl.inspect_data --rows 5
"""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path
from typing import Any

import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parent.parent

PICKLES = [
    "movies.pkl",
    "movies_metadata.pkl",
    "credits.pkl",
    "keywords.pkl",
    "links.pkl",
    "vectors.pkl",
    "model.pkl",
]

RULE = "=" * 78
SUB = "-" * 78


def _load(path: Path) -> Any:
    """Load a pickle, preferring pandas so DataFrames round-trip correctly."""
    try:
        return pd.read_pickle(path)
    except Exception:  # noqa: BLE001 - fall back to plain pickle for non-pandas objects
        with path.open("rb") as handle:
            return pickle.load(handle)


def _truncate(value: Any, limit: int = 220) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + f"... [+{len(text) - limit} chars]"


def _describe_dataframe(name: str, df: pd.DataFrame, sample_rows: int) -> None:
    print(f"shape        : {df.shape[0]:,} rows x {df.shape[1]} cols")
    print(f"memory       : {df.memory_usage(deep=True).sum() / 1e6:,.1f} MB")
    print(f"index        : {type(df.index).__name__} "
          f"unique={df.index.is_unique} monotonic={df.index.is_monotonic_increasing}")
    print(SUB)
    print(f"{'column':<26} {'dtype':<22} {'nulls':>8} {'unique':>10}")
    print(SUB)
    for col in df.columns:
        series = df[col]
        nulls = int(series.isna().sum())
        try:
            unique = f"{series.nunique(dropna=True):,}"
        except TypeError:
            unique = "unhashable"
        print(f"{str(col):<26} {str(series.dtype):<22} {nulls:>8,} {unique:>10}")

    print(SUB)
    print("SAMPLE VALUES (first non-null per column):")
    for col in df.columns:
        series = df[col].dropna()
        sample = series.iloc[0] if len(series) else None
        print(f"  {col}:")
        print(f"    type={type(sample).__name__}  value={_truncate(sample)}")

    if sample_rows:
        print(SUB)
        print(f"HEAD ({sample_rows} rows, transposed):")
        with pd.option_context(
            "display.max_colwidth", 90, "display.width", 200, "display.max_rows", 200
        ):
            print(df.head(sample_rows).T)


def _describe_other(name: str, obj: Any) -> None:
    print(f"python type  : {type(obj).__module__}.{type(obj).__name__}")
    for attr in ("shape", "dtype", "nnz", "format", "size", "ndim"):
        if hasattr(obj, attr):
            try:
                print(f"{attr:<13}: {getattr(obj, attr)}")
            except Exception as exc:  # noqa: BLE001
                print(f"{attr:<13}: <error: {exc}>")

    if hasattr(obj, "get_params"):
        print("estimator params:")
        try:
            for key, value in sorted(obj.get_params().items()):
                print(f"    {key} = {value!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"    <error reading params: {exc}>")

    if hasattr(obj, "nnz") and hasattr(obj, "shape"):
        rows, cols = obj.shape
        density = obj.nnz / (rows * cols) if rows and cols else 0
        print(f"density      : {density:.6%} ({obj.nnz:,} stored values)")

    if isinstance(obj, (list, tuple, dict)):
        print(f"length       : {len(obj):,}")
        preview = list(obj)[:5] if not isinstance(obj, dict) else list(obj.items())[:5]
        print(f"preview      : {_truncate(preview, 400)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect raw VaultStream pickles.")
    parser.add_argument(
        "--rows", type=int, default=0, help="Also print N transposed head rows."
    )
    args = parser.parse_args()

    pd.set_option("display.max_columns", None)

    for filename in PICKLES:
        path = BACKEND_ROOT / filename
        print()
        print(RULE)
        print(f"FILE: {filename}")
        print(RULE)

        if not path.exists():
            print("  !! MISSING")
            continue

        print(f"size on disk : {path.stat().st_size / 1e6:,.1f} MB")
        try:
            obj = _load(path)
        except Exception as exc:  # noqa: BLE001
            print(f"  !! FAILED TO LOAD: {type(exc).__name__}: {exc}")
            continue

        if isinstance(obj, pd.DataFrame):
            _describe_dataframe(filename, obj, args.rows)
        elif isinstance(obj, pd.Series):
            print(f"Series: len={len(obj):,} dtype={obj.dtype} name={obj.name}")
            print(f"sample: {_truncate(obj.head(3).tolist())}")
        else:
            _describe_other(filename, obj)

    print()
    print(RULE)
    print("Inspection complete. Nothing was modified.")
    print(RULE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
