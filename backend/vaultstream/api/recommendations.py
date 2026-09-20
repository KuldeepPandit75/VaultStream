"""Recommendation endpoints.

``/movies/{row_index}/similar`` is public. The personalised endpoints require a
session, since they are derived from watch history.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from vaultstream.api.deps import CurrentUser
from vaultstream.db import get_db
from vaultstream.models.catalog import Movie
from vaultstream.schemas.catalog import MovieSummary
from vaultstream.schemas.recommendations import RecommendationFeed, RecommendationRow
from vaultstream.services import history as history_service
from vaultstream.services import recommender

router = APIRouter(tags=["recommendations"])


@router.get(
    "/movies/{row_index}/similar",
    response_model=list[MovieSummary],
    summary="Titles similar to a given one",
    responses={404: {"description": "No movie with that row_index"}},
)
def similar_movies(
    db: Annotated[Session, Depends(get_db)],
    row_index: Annotated[int, Path(ge=0)],
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
) -> list[MovieSummary]:
    """Public: no session needed, so it can appear on any detail page."""
    if db.get(Movie, row_index) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No movie with row_index {row_index}",
        )
    return recommender.similar_to(db, row_index, limit=limit)


@router.get(
    "/recommendations/for-you",
    response_model=RecommendationRow,
    summary="One blended row built from the user's whole recent history",
)
def for_you(
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> RecommendationRow:
    items = recommender.for_you(db, user.id, limit=limit)

    if items:
        return RecommendationRow(
            key="for-you",
            title="Top picks for you",
            reason="Based on everything you have watched recently",
            personalised=True,
            items=items,
        )

    # Cold start: say so rather than presenting popularity as personalisation.
    watched = history_service.watched_row_indexes(db, user.id)
    return RecommendationRow(
        key="popular",
        title="Popular on VaultStream",
        reason="Watch something to start getting personalised picks",
        personalised=False,
        items=recommender.popular_fallback(db, limit=limit, exclude=watched),
    )


@router.get(
    "/recommendations/because-you-watched",
    response_model=list[RecommendationRow],
    summary="One row per recently watched title",
)
def because_you_watched(
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    rows: Annotated[int, Query(ge=1, le=6)] = 3,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[RecommendationRow]:
    pairs = recommender.because_you_watched(db, user.id, rows=rows, limit=limit)
    return [
        RecommendationRow(
            key=f"because-{seed.row_index}",
            title=f"Because you watched {seed.title}",
            reason=None,
            personalised=True,
            seed=seed,
            items=items,
        )
        for seed, items in pairs
    ]


@router.get(
    "/recommendations/feed",
    response_model=RecommendationFeed,
    summary="The full personalised block for the home page",
)
def feed(
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> RecommendationFeed:
    """Assembled server-side so the home page needs one request, not four."""
    rows: list[RecommendationRow] = []

    picks = recommender.for_you(db, user.id, limit=limit)
    has_history = bool(picks)

    if picks:
        rows.append(
            RecommendationRow(
                key="for-you",
                title="Top picks for you",
                reason="Based on everything you have watched recently",
                personalised=True,
                items=picks,
            )
        )

    for seed, items in recommender.because_you_watched(db, user.id, limit=limit):
        rows.append(
            RecommendationRow(
                key=f"because-{seed.row_index}",
                title=f"Because you watched {seed.title}",
                personalised=True,
                seed=seed,
                items=items,
            )
        )

    if not rows:
        watched = history_service.watched_row_indexes(db, user.id)
        rows.append(
            RecommendationRow(
                key="popular",
                title="Popular on VaultStream",
                reason="Watch something to start getting personalised picks",
                personalised=False,
                items=recommender.popular_fallback(db, limit=limit, exclude=watched),
            )
        )

    return RecommendationFeed(rows=rows, has_history=has_history)


@router.get(
    "/recommendations/health",
    tags=["ops"],
    summary="Vector index status and alignment check",
)
def recommender_health(db: Annotated[Session, Depends(get_db)]) -> dict[str, object]:
    """Confirms the matrix is loadable and still aligned to the catalogue."""
    try:
        index = recommender.get_index()
        recommender.verify_alignment(db)
        aligned = True
        detail = None
    except Exception as exc:  # noqa: BLE001 - report rather than 500
        return {"loaded": False, "aligned": False, "detail": str(exc)}

    return {
        "loaded": True,
        "aligned": aligned,
        "detail": detail,
        "rows": index.n_rows,
        "features": int(index.matrix.shape[1]),
        "non_zeros": int(index.matrix.nnz),
        "memory_mb": round(
            (
                index.matrix.data.nbytes
                + index.matrix.indices.nbytes
                + index.matrix.indptr.nbytes
            )
            / 1e6,
            1,
        ),
    }
