"""READ-ONLY integrity probes for the specific hazards found during inspection.

Answers questions the generic column profile cannot:
  * Are duplicate rows in movies.pkl identical, or do they disagree?
  * What are the 5 distinct `adult` values, and which rows are malformed?
  * How sparse is the dense int64 vector matrix really?
  * Does movies.pkl join cleanly onto the other frames?

Usage:
    python -m etl.probe_integrity
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parent.parent
RULE = "=" * 78


def probe_movies_duplicates() -> pd.DataFrame:
    print(RULE)
    print("PROBE 1: duplicate ids inside movies.pkl")
    print(RULE)
    movies = pd.read_pickle(BACKEND_ROOT / "movies.pkl")
    total, unique = len(movies), movies["id"].nunique()
    print(f"rows={total:,} unique_ids={unique:,} duplicate_rows={total - unique:,}")

    dup_mask = movies["id"].duplicated(keep=False)
    dups = movies[dup_mask].sort_values("id")
    print(f"rows involved in any duplication: {len(dups):,}")

    # Are duplicated groups fully identical across every column?
    fully_identical = int(movies.duplicated(keep=False).sum())
    print(f"rows that are exact full-row duplicates: {fully_identical:,}")

    # Do duplicate ids ever disagree on title or tags?
    grouped = dups.groupby("id").agg(
        titles=("title", "nunique"), tags=("tags", "nunique")
    )
    print(f"duplicate ids disagreeing on title: {(grouped['titles'] > 1).sum():,}")
    print(f"duplicate ids disagreeing on tags : {(grouped['tags'] > 1).sum():,}")

    print("\nexample duplicate group:")
    example_id = dups["id"].iloc[0]
    sample = movies[movies["id"] == example_id][["id", "title", "poster_path"]]
    print(sample.to_string())
    print(f"tags equal within group: {movies[movies['id'] == example_id]['tags'].nunique() == 1}")
    return movies


def probe_adult_and_malformed() -> None:
    print()
    print(RULE)
    print("PROBE 2: `adult` values and malformed rows in movies_metadata.pkl")
    print(RULE)
    meta = pd.read_pickle(BACKEND_ROOT / "movies_metadata.pkl")
    print("adult value counts:")
    print(meta["adult"].value_counts(dropna=False).to_string())

    bad = ~meta["adult"].isin(["True", "False"])
    print(f"\nmalformed rows (adult not True/False): {int(bad.sum())}")
    if bad.any():
        cols = ["id", "title", "adult", "budget", "release_date", "popularity"]
        print(meta.loc[bad, cols].to_string())

    print("\nrows where id is not a clean integer:")
    non_int = meta["id"][pd.to_numeric(meta["id"], errors="coerce").isna()]
    print(non_int.to_string() if len(non_int) else "  none")

    numeric_id = pd.to_numeric(meta["id"], errors="coerce")
    print(f"\nduplicate ids in metadata: {int(numeric_id.duplicated().sum())}")
    print("adult=='True' count (to be excluded from catalog): "
          f"{int((meta['adult'] == 'True').sum())}")


def probe_vector_sparsity() -> None:
    print()
    print(RULE)
    print("PROBE 3: vector matrix sparsity and memory")
    print(RULE)
    vectors = pd.read_pickle(BACKEND_ROOT / "vectors.pkl")
    rows, cols = vectors.shape
    dense_mb = vectors.nbytes / 1e6
    nnz = int(np.count_nonzero(vectors))
    density = nnz / (rows * cols)
    # CSR float32: 4 bytes data + 4 bytes int32 index per nnz, plus row pointers.
    csr_mb = (nnz * 8 + (rows + 1) * 4) / 1e6
    print(f"shape={rows:,} x {cols:,}  dtype={vectors.dtype}")
    print(f"dense in memory : {dense_mb:,.1f} MB")
    print(f"non-zero entries: {nnz:,}  density={density:.4%}")
    print(f"as CSR float32  : {csr_mb:,.1f} MB  "
          f"({dense_mb / csr_mb:,.0f}x smaller)")
    print(f"max cell value  : {vectors.max()}  (1 => binary, >1 => counts)")
    per_row = np.count_nonzero(vectors, axis=1)
    print(f"tokens per movie: min={per_row.min()} median={int(np.median(per_row))} "
          f"max={per_row.max()}")
    print(f"all-zero rows   : {int((per_row == 0).sum()):,}")


def probe_joins(movies: pd.DataFrame) -> None:
    print()
    print(RULE)
    print("PROBE 4: join coverage of movies.pkl against the other frames")
    print(RULE)
    ids = pd.Index(movies["id"].unique())
    print(f"distinct movie ids to satisfy: {len(ids):,}")

    meta = pd.read_pickle(BACKEND_ROOT / "movies_metadata.pkl")
    meta_ids = pd.Index(pd.to_numeric(meta["id"], errors="coerce").dropna().astype("int64").unique())
    print(f"movies_metadata : {ids.isin(meta_ids).sum():,} matched  "
          f"{(~ids.isin(meta_ids)).sum():,} missing")

    credits = pd.read_pickle(BACKEND_ROOT / "credits.pkl")
    credit_ids = pd.Index(credits["id"].unique())
    print(f"credits         : {ids.isin(credit_ids).sum():,} matched  "
          f"{(~ids.isin(credit_ids)).sum():,} missing")

    keywords = pd.read_pickle(BACKEND_ROOT / "keywords.pkl")
    keyword_ids = pd.Index(keywords["id"].unique())
    print(f"keywords        : {ids.isin(keyword_ids).sum():,} matched  "
          f"{(~ids.isin(keyword_ids)).sum():,} missing")

    links = pd.read_pickle(BACKEND_ROOT / "links.pkl")
    link_ids = pd.Index(links["tmdbId"].dropna().astype("int64").unique())
    print(f"links (tmdbId)  : {ids.isin(link_ids).sum():,} matched  "
          f"{(~ids.isin(link_ids)).sum():,} missing")


def main() -> int:
    pd.set_option("display.width", 200)
    pd.set_option("display.max_colwidth", 40)
    movies = probe_movies_duplicates()
    probe_adult_and_malformed()
    probe_vector_sparsity()
    probe_joins(movies)
    print()
    print(RULE)
    print("Probes complete. Nothing was modified.")
    print(RULE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
