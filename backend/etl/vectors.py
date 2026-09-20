"""Convert the dense feature matrix into a compact sparse artifact.

Why this exists
---------------
``vectors.pkl`` is a dense int64 array of shape (45264, 5000) -- 1.81 GB in RAM
and on disk. It is a bag-of-words count matrix, so it is overwhelmingly zeros.
``model.pkl`` is another 1.81 GB because a ``brute``-metric NearestNeighbors
stores its entire training matrix internally.

We therefore persist only an L2-normalised CSR float32 matrix. That makes the
artifact small enough to load at startup, and lets cosine similarity be a plain
sparse dot product. The KNN index is refitted at startup, which also removes the
sklearn-version fragility of unpickling a fitted estimator.

Row order is preserved exactly: row i of the output is row i of movies.pkl.
A parallel ``vector_row_map.npy`` records the tmdb_id for each row so alignment
can be asserted at runtime.

Usage:
    python -m etl.vectors
    python -m etl.vectors --force
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_ROOT / "data"
VECTORS_NPZ = DATA_DIR / "vectors.npz"
ROW_MAP_NPY = DATA_DIR / "vector_row_map.npy"

# Rows converted per block. Keeps peak memory close to the source array size
# instead of doubling it.
CHUNK_ROWS = 4096


def _l2_normalize(matrix: sp.csr_matrix) -> sp.csr_matrix:
    """Scale each row to unit L2 norm so cosine similarity == dot product.

    Zero rows are left as zeros rather than producing NaN.
    """
    matrix = matrix.tocsr(copy=True)
    matrix.data = matrix.data.astype(np.float32, copy=False)

    # Per-row L2 norm computed from the CSR data array directly, then applied by
    # repeating each row's scale factor across that row's stored values. Avoids
    # building a 45k x 45k diagonal matrix and a sparse matmul.
    squared = matrix.data * matrix.data
    row_lengths = np.diff(matrix.indptr)

    if squared.size == 0:
        # The whole matrix is empty (every row has zero stored values).
        # reduceat requires at least one valid index into a non-empty array,
        # so there is nothing to reduce -- every row's norm is just 0.
        norms = np.zeros(row_lengths.shape[0], dtype=np.float64)
    else:
        # reduceat requires every index to be < len(squared). A row (or a run
        # of trailing rows) with zero stored values pushes indptr[:-1] up to
        # exactly len(squared) once it is the last row -- e.g. a movie with no
        # tags/features at all sits at the end of the matrix. Clip those
        # indices into range; reduceat then yields a garbage value for that
        # slot, which the row_lengths == 0 masking below discards anyway.
        safe_starts = np.minimum(matrix.indptr[:-1], squared.size - 1)
        norms = np.sqrt(np.add.reduceat(squared, safe_starts))
    # reduceat yields a garbage entry for empty rows; force those to zero.
    norms[row_lengths == 0] = 0.0

    inverse = np.zeros_like(norms, dtype=np.float32)
    nonzero = norms > 0
    inverse[nonzero] = (1.0 / norms[nonzero]).astype(np.float32)

    matrix.data *= np.repeat(inverse, row_lengths)
    return matrix


def densify_to_csr(dense: np.ndarray, chunk_rows: int = CHUNK_ROWS) -> sp.csr_matrix:
    """Convert a large dense array to CSR float32 in row blocks."""
    blocks: list[sp.csr_matrix] = []
    total = dense.shape[0]
    for start in range(0, total, chunk_rows):
        block = dense[start : start + chunk_rows]
        blocks.append(sp.csr_matrix(block.astype(np.float32, copy=False)))
    return sp.vstack(blocks, format="csr", dtype=np.float32)


def build(force: bool = False, root: Path = BACKEND_ROOT) -> dict[str, object]:
    """Build vectors.npz + vector_row_map.npy. Returns a stats dict."""
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    vectors_npz = data_dir / "vectors.npz"
    row_map_npy = data_dir / "vector_row_map.npy"

    if vectors_npz.exists() and row_map_npy.exists() and not force:
        existing = sp.load_npz(vectors_npz)
        return {
            "skipped": True,
            "reason": "artifacts already exist (use --force to rebuild)",
            "shape": existing.shape,
            "output": str(vectors_npz),
        }

    started = time.perf_counter()

    movies = pd.read_pickle(root / "movies.pkl")
    dense = pd.read_pickle(root / "vectors.pkl")

    if not isinstance(dense, np.ndarray):
        raise TypeError(f"vectors.pkl is {type(dense)!r}, expected numpy.ndarray")
    if dense.shape[0] != len(movies):
        raise ValueError(
            f"Alignment broken: vectors has {dense.shape[0]:,} rows but "
            f"movies.pkl has {len(movies):,}. Refusing to write."
        )

    dense_bytes = dense.nbytes
    nnz_total = int(np.count_nonzero(dense))

    sparse = densify_to_csr(dense)
    del dense  # release the 1.8 GB source before normalising

    normalised = _l2_normalize(sparse)
    del sparse

    sp.save_npz(vectors_npz, normalised, compressed=True)

    row_map = movies["id"].to_numpy(dtype=np.int64, copy=True)
    np.save(row_map_npy, row_map)

    elapsed = time.perf_counter() - started
    rows, cols = normalised.shape
    return {
        "skipped": False,
        "rows": rows,
        "cols": cols,
        "nnz": int(normalised.nnz),
        "nnz_source": nnz_total,
        "density_pct": round(normalised.nnz / (rows * cols) * 100, 4),
        "dense_mb": round(dense_bytes / 1e6, 1),
        "sparse_memory_mb": round(
            (normalised.data.nbytes + normalised.indices.nbytes + normalised.indptr.nbytes)
            / 1e6,
            1,
        ),
        "npz_on_disk_mb": round(vectors_npz.stat().st_size / 1e6, 1),
        "row_map_len": int(row_map.shape[0]),
        "elapsed_s": round(elapsed, 1),
        "output": str(vectors_npz),
        "row_map": str(row_map_npy),
    }


def load_vectors(root: Path = BACKEND_ROOT) -> tuple[sp.csr_matrix, np.ndarray]:
    """Load the sparse matrix and its row -> tmdb_id map.

    Raises a clear error if the artifacts are missing or disagree in length.
    """
    data_dir = root / "data"
    vectors_npz = data_dir / "vectors.npz"
    row_map_npy = data_dir / "vector_row_map.npy"

    if not vectors_npz.exists() or not row_map_npy.exists():
        raise FileNotFoundError(
            "Vector artifacts missing. Build them with: python -m etl.vectors"
        )

    matrix = sp.load_npz(vectors_npz).tocsr()
    row_map = np.load(row_map_npy)
    if matrix.shape[0] != row_map.shape[0]:
        raise ValueError(
            f"Vector/row-map length mismatch: {matrix.shape[0]:,} vs {row_map.shape[0]:,}"
        )
    return matrix, row_map


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the sparse vector artifact.")
    parser.add_argument("--force", action="store_true", help="Rebuild even if present.")
    args = parser.parse_args()

    stats = build(force=args.force)
    rule = "=" * 68
    print(rule)
    print("Vector artifact")
    print(rule)
    for key, value in stats.items():
        print(f"  {key:<18}: {value}")
    if not stats.get("skipped"):
        shrink = float(stats["dense_mb"]) / float(stats["npz_on_disk_mb"])  # type: ignore[arg-type]
        print(f"  {'shrink_factor':<18}: {shrink:,.0f}x smaller on disk")
    print(rule)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
