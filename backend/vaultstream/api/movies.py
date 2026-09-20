"""Public catalog endpoints.

The movie path parameter is ``row_index`` (the catalog primary key), not
``tmdb_id``, because the curated catalog contains duplicate tmdb_ids.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from vaultstream.config import get_settings
from vaultstream.db import get_db
from vaultstream.models.catalog import Movie
from vaultstream.schemas.catalog import (
    GenreOut,
    MovieDetail,
    MovieSummary,
    Page,
    SortField,
    SortOrder,
    StreamSource,
)
from vaultstream.services import catalog as catalog_service
from vaultstream.services import media as media_service
from vaultstream.services.catalog import MovieFilters

router = APIRouter(tags=["catalog"])


@router.get("/genres", response_model=list[GenreOut], summary="All genres")
def get_genres(db: Annotated[Session, Depends(get_db)]) -> list[GenreOut]:
    return catalog_service.list_genres(db)


@router.get("/languages", summary="Languages present in the catalog")
def get_languages(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 40,
) -> list[dict[str, object]]:
    return catalog_service.list_languages(db, limit=limit)


@router.get("/movies/filters", summary="Filter bounds for the browse UI")
def get_filter_bounds(db: Annotated[Session, Depends(get_db)]) -> dict[str, object]:
    settings = get_settings()
    return {
        "genres": [genre.model_dump() for genre in catalog_service.list_genres(db)],
        "languages": catalog_service.list_languages(db),
        **catalog_service.year_bounds(db),
        "default_page_size": settings.default_page_size,
        "max_page_size": settings.max_page_size,
        "quality_floor_vote_count": settings.quality_floor_vote_count,
    }


@router.get(
    "/movies",
    response_model=Page[MovieSummary],
    summary="Browse, search, filter and sort the catalog",
)
def list_movies(
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str | None, Query(max_length=200, description="Substring title search")] = None,
    genre: Annotated[
        list[str] | None,
        Query(description="Genre name or id. Repeatable. OR by default."),
    ] = None,
    genre_match_all: Annotated[
        bool, Query(description="Require every supplied genre instead of any.")
    ] = False,
    year_from: Annotated[int | None, Query(ge=1870, le=2100)] = None,
    year_to: Annotated[int | None, Query(ge=1870, le=2100)] = None,
    language: Annotated[str | None, Query(max_length=20)] = None,
    min_rating: Annotated[float | None, Query(ge=0, le=10)] = None,
    min_votes: Annotated[int | None, Query(ge=0)] = None,
    include_adult: bool = False,
    include_low_quality: Annotated[
        bool, Query(description="Bypass the has-poster / min-votes browse floor.")
    ] = False,
    sort: SortField = SortField.POPULARITY,
    order: SortOrder = SortOrder.DESC,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> Page[MovieSummary]:
    settings = get_settings()
    effective_page_size = page_size or settings.default_page_size
    # Hard cap: an unbounded page_size would let one request pull 45k rows.
    effective_page_size = min(effective_page_size, settings.max_page_size)

    if year_from is not None and year_to is not None and year_from > year_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="year_from must not be greater than year_to",
        )

    filters = MovieFilters(
        query=q,
        genres=genre or [],
        genre_match_all=genre_match_all,
        year_from=year_from,
        year_to=year_to,
        language=language,
        min_rating=min_rating,
        min_votes=min_votes,
        include_adult=include_adult,
        include_low_quality=include_low_quality,
    )

    items, total = catalog_service.list_movies(
        db,
        filters,
        page=page,
        page_size=effective_page_size,
        sort=sort,
        order=order,
    )
    return Page.build(items, total, page, effective_page_size)


@router.get(
    "/movies/{row_index}",
    response_model=MovieDetail,
    summary="Full detail for one catalog row",
    responses={404: {"description": "No movie with that row_index"}},
)
def get_movie(
    db: Annotated[Session, Depends(get_db)],
    row_index: Annotated[int, Path(ge=0, description="Catalog primary key")],
) -> MovieDetail:
    detail = catalog_service.get_movie_detail(db, row_index)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No movie with row_index {row_index}",
        )
    return detail


@router.get(
    "/movies/{row_index}/stream",
    response_model=StreamSource,
    summary="Resolve the playback source for a title",
    responses={
        404: {"description": "Movie not found, or no trailer is available"},
        503: {"description": "Media resolution is not configured"},
    },
)
def get_stream_source(
    db: Annotated[Session, Depends(get_db)],
    row_index: Annotated[int, Path(ge=0)],
) -> StreamSource:
    """Return a playback descriptor.

    This is the seam that keeps the player decoupled from the source: the client
    receives ``{type, key}`` and never learns where the media came from.
    """
    movie = db.get(Movie, row_index)
    if movie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No movie with row_index {row_index}",
        )

    media = media_service.resolve(db, movie.tmdb_id)

    if media is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Trailer lookup is not configured. Set TMDB_API_KEY in the "
                "backend environment."
            ),
        )

    if not media.trailer_key:
        # A deliberate, explainable 404 rather than an empty 200, so the player
        # can show a specific message.
        reason = (
            "This title is not listed on TMDB."
            if media.not_found
            else "No trailer is available for this title."
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=reason)

    return StreamSource(
        row_index=movie.row_index,
        tmdb_id=movie.tmdb_id,
        title=movie.title,
        type="youtube",
        key=media.trailer_key,
        name=media.trailer_name,
        video_type=media.trailer_type,
    )


@router.get("/media/coverage", tags=["ops"], summary="Media cache coverage")
def get_media_coverage(db: Annotated[Session, Depends(get_db)]) -> dict[str, object]:
    """How much of the catalogue has refreshed artwork and trailers."""
    settings = get_settings()
    distinct_titles = catalog_service.distinct_title_count(db)
    stats = media_service.coverage(db)
    return {
        "configured": bool(settings.tmdb_api_key),
        "distinct_titles": distinct_titles,
        **stats,
        "poster_coverage_pct": (
            round(stats["with_poster"] / distinct_titles * 100, 2)
            if distinct_titles
            else 0.0
        ),
    }
