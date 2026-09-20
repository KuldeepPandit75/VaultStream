"""Catalog queries: listing, filtering, search, and detail assembly."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Select, and_, distinct, false, func, or_, select, true
from sqlalchemy.orm import Session

from vaultstream.config import get_settings
from vaultstream.models.catalog import (
    Collection,
    Genre,
    Keyword,
    Movie,
    MovieCredit,
    MovieGenre,
    MovieKeyword,
    Person,
)
from vaultstream.schemas.catalog import (
    CastMemberOut,
    CollectionOut,
    CrewMemberOut,
    GenreOut,
    KeywordOut,
    MovieDetail,
    MovieSummary,
    SortField,
    SortOrder,
)
from vaultstream.models.media import MovieMedia
from vaultstream.services import media as media_service
from vaultstream.services.images import backdrop_url, imdb_url, poster_url, profile_url

# Crew jobs that read as "directed by" on a detail page.
DIRECTOR_JOBS = ("Director",)

# Display precedence for crew on the detail page. Without this, crew would come
# back alphabetically by name and the director could appear below a producer.
CREW_JOB_PRIORITY = {
    "Director": 0,
    "Screenplay": 1,
    "Writer": 2,
    "Story": 3,
    "Producer": 4,
}


@dataclass(slots=True)
class MovieFilters:
    """Normalised browse filters."""

    query: str | None = None
    genres: list[str] = field(default_factory=list)
    genre_match_all: bool = False
    year_from: int | None = None
    year_to: int | None = None
    language: str | None = None
    min_rating: float | None = None
    min_votes: int | None = None
    include_adult: bool = False
    # Bypasses the "has poster + enough votes" browse floor.
    include_low_quality: bool = False


def _quality_predicates(filters: MovieFilters) -> list:
    """Conditions that keep near-empty and adult records off browse surfaces."""
    settings = get_settings()
    predicates = []

    if not filters.include_adult:
        predicates.append(Movie.adult.is_(False))

    if not filters.include_low_quality:
        predicates.append(Movie.poster_path.isnot(None))
        floor = (
            filters.min_votes
            if filters.min_votes is not None
            else settings.quality_floor_vote_count
        )
        predicates.append(Movie.vote_count >= floor)
    elif filters.min_votes is not None:
        predicates.append(Movie.vote_count >= filters.min_votes)

    return predicates


def _filter_predicates(session: Session, filters: MovieFilters) -> list:
    predicates = _quality_predicates(filters)

    if filters.query:
        # Trigram GIN index backs this ILIKE, so substring search stays fast.
        pattern = f"%{filters.query.strip()}%"
        predicates.append(
            or_(Movie.title.ilike(pattern), Movie.original_title.ilike(pattern))
        )

    if filters.year_from is not None:
        predicates.append(Movie.release_year >= filters.year_from)
    if filters.year_to is not None:
        predicates.append(Movie.release_year <= filters.year_to)

    if filters.language:
        predicates.append(Movie.original_language == filters.language.lower())

    if filters.min_rating is not None:
        predicates.append(Movie.vote_average >= filters.min_rating)

    if filters.genres:
        genre_ids = _resolve_genre_ids(session, filters.genres)
        if not genre_ids:
            # Unknown genre name: match nothing rather than silently ignoring it.
            # false() renders the SQL literal FALSE; func.false() would emit a
            # bogus false() function call.
            predicates.append(false())
        elif filters.genre_match_all:
            for genre_id in genre_ids:
                predicates.append(
                    select(MovieGenre.tmdb_id)
                    .where(
                        MovieGenre.tmdb_id == Movie.tmdb_id,
                        MovieGenre.genre_id == genre_id,
                    )
                    .exists()
                )
        else:
            predicates.append(
                select(MovieGenre.tmdb_id)
                .where(
                    MovieGenre.tmdb_id == Movie.tmdb_id,
                    MovieGenre.genre_id.in_(genre_ids),
                )
                .exists()
            )

    return predicates


def _resolve_genre_ids(session: Session, names: list[str]) -> list[int]:
    """Map genre names (case-insensitive) to ids; numeric input passes through."""
    wanted_names: list[str] = []
    ids: list[int] = []
    for value in names:
        text = str(value).strip()
        if not text:
            continue
        if text.isdigit():
            ids.append(int(text))
        else:
            wanted_names.append(text.lower())

    if wanted_names:
        rows = session.execute(
            select(Genre.id).where(func.lower(Genre.name).in_(wanted_names))
        ).scalars()
        ids.extend(rows)
    return sorted(set(ids))


def _order_by(sort: SortField, order: SortOrder) -> list:
    """Sort expression with NULLs last and a stable tiebreaker.

    row_index breaks ties so that pagination cannot repeat or skip rows when
    many movies share a popularity or rating value.
    """
    column = {
        SortField.POPULARITY: Movie.popularity,
        SortField.RATING: Movie.vote_average,
        SortField.RELEASE_DATE: Movie.release_date,
        SortField.TITLE: Movie.title,
        SortField.VOTE_COUNT: Movie.vote_count,
    }[sort]

    if order is SortOrder.ASC:
        primary = column.asc().nulls_last()
    else:
        primary = column.desc().nulls_last()
    return [primary, Movie.row_index.asc()]


def _deduplicated_row_indexes(predicates: list) -> Select:
    """One row_index per tmdb_id.

    The curated catalog repeats 1,142 rows verbatim; without this a browse grid
    would show the same film several times. The lowest row_index wins.
    """
    return (
        select(func.min(Movie.row_index).label("row_index"))
        .where(and_(*predicates) if predicates else true())
        .group_by(Movie.tmdb_id)
    )


def count_movies(session: Session, filters: MovieFilters) -> int:
    predicates = _filter_predicates(session, filters)
    statement = select(func.count(distinct(Movie.tmdb_id)))
    if predicates:
        statement = statement.where(and_(*predicates))
    return int(session.execute(statement).scalar_one())


def list_movies(
    session: Session,
    filters: MovieFilters,
    *,
    page: int,
    page_size: int,
    sort: SortField = SortField.POPULARITY,
    order: SortOrder = SortOrder.DESC,
) -> tuple[list[MovieSummary], int]:
    """Return one page of movie summaries plus the total distinct match count."""
    predicates = _filter_predicates(session, filters)
    total = count_movies(session, filters)
    if total == 0:
        return [], 0

    unique_rows = _deduplicated_row_indexes(predicates).subquery("unique_rows")

    statement = (
        select(Movie)
        .join(unique_rows, Movie.row_index == unique_rows.c.row_index)
        .order_by(*_order_by(sort, order))
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    movies = list(session.execute(statement).scalars().all())
    tmdb_ids = [movie.tmdb_id for movie in movies]
    genre_map = _genre_names_for(session, tmdb_ids)
    # One batched cache read for the whole page rather than per-card lookups.
    media_map = media_service.get_cached_many(session, tmdb_ids)

    return [
        _to_summary(movie, genre_map.get(movie.tmdb_id, []), media_map.get(movie.tmdb_id))
        for movie in movies
    ], total


def _genre_names_for(session: Session, tmdb_ids: list[int]) -> dict[int, list[str]]:
    """Fetch genres for a whole page in one query (avoids N+1)."""
    if not tmdb_ids:
        return {}
    rows = session.execute(
        select(MovieGenre.tmdb_id, Genre.name)
        .join(Genre, Genre.id == MovieGenre.genre_id)
        .where(MovieGenre.tmdb_id.in_(set(tmdb_ids)))
        .order_by(MovieGenre.tmdb_id, Genre.name)
    ).all()
    result: dict[int, list[str]] = {}
    for tmdb_id, name in rows:
        result.setdefault(tmdb_id, []).append(name)
    return result


def _to_summary(
    movie: Movie, genres: list[str], media: MovieMedia | None = None
) -> MovieSummary:
    poster_path, backdrop_path = media_service.effective_artwork(
        movie.poster_path, movie.backdrop_path, media
    )
    return MovieSummary(
        row_index=movie.row_index,
        tmdb_id=movie.tmdb_id,
        title=movie.title,
        release_year=movie.release_year,
        runtime=movie.runtime,
        vote_average=movie.vote_average,
        vote_count=movie.vote_count,
        popularity=movie.popularity,
        poster_path=poster_path,
        poster_url=poster_url(poster_path),
        backdrop_url=backdrop_url(backdrop_path),
        genres=genres,
    )


def get_movie_detail(
    session: Session, row_index: int, *, resolve_media: bool = True
) -> MovieDetail | None:
    """Assemble the full detail payload, or None when the row does not exist.

    The detail page is a single-movie view, so it is the natural place to resolve
    media lazily: one TMDB call warms the cache for artwork and the trailer that
    the player will need next.
    """
    movie = session.get(Movie, row_index)
    if movie is None:
        return None

    media = (
        media_service.resolve(session, movie.tmdb_id)
        if resolve_media
        else media_service.get_cached(session, movie.tmdb_id)
    )
    poster_path, backdrop_path = media_service.effective_artwork(
        movie.poster_path, movie.backdrop_path, media
    )

    genre_names = _genre_names_for(session, [movie.tmdb_id]).get(movie.tmdb_id, [])

    keywords = [
        KeywordOut(id=keyword_id, name=name)
        for keyword_id, name in session.execute(
            select(Keyword.id, Keyword.name)
            .join(MovieKeyword, MovieKeyword.keyword_id == Keyword.id)
            .where(MovieKeyword.tmdb_id == movie.tmdb_id)
            .order_by(Keyword.name)
        ).all()
    ]

    credit_rows = session.execute(
        select(
            MovieCredit.credit_type,
            MovieCredit.role,
            MovieCredit.department,
            MovieCredit.billing_order,
            Person.id,
            Person.name,
            Person.profile_path,
        )
        .join(Person, Person.id == MovieCredit.person_id)
        .where(MovieCredit.tmdb_id == movie.tmdb_id)
        .order_by(
            MovieCredit.credit_type,
            MovieCredit.billing_order.asc().nulls_last(),
            Person.name,
        )
    ).all()

    cast: list[CastMemberOut] = []
    crew: list[CrewMemberOut] = []
    for row in credit_rows:
        if row.credit_type == "cast":
            cast.append(
                CastMemberOut(
                    person_id=row.id,
                    name=row.name,
                    character=row.role,
                    billing_order=row.billing_order,
                    profile_url=profile_url(row.profile_path),
                )
            )
        else:
            crew.append(
                CrewMemberOut(
                    person_id=row.id,
                    name=row.name,
                    job=row.role or "",
                    department=row.department,
                    profile_url=profile_url(row.profile_path),
                )
            )

    collection: CollectionOut | None = None
    if movie.collection_id is not None:
        record = session.get(Collection, movie.collection_id)
        if record is not None:
            collection = CollectionOut(
                id=record.id,
                name=record.name,
                poster_url=poster_url(record.poster_path),
                backdrop_url=backdrop_url(record.backdrop_path),
            )

    crew.sort(key=lambda member: (CREW_JOB_PRIORITY.get(member.job, 99), member.name))

    return MovieDetail(
        row_index=movie.row_index,
        tmdb_id=movie.tmdb_id,
        title=movie.title,
        release_year=movie.release_year,
        runtime=movie.runtime,
        vote_average=movie.vote_average,
        vote_count=movie.vote_count,
        popularity=movie.popularity,
        poster_path=poster_path,
        poster_url=poster_url(poster_path),
        backdrop_url=backdrop_url(backdrop_path),
        genres=genre_names,
        has_trailer=bool(media and media.trailer_key),
        imdb_id=movie.imdb_id,
        imdb_url=imdb_url(movie.imdb_id),
        original_title=movie.original_title,
        original_language=movie.original_language,
        tagline=movie.tagline,
        overview=movie.overview,
        release_date=movie.release_date,
        status=movie.status,
        homepage=movie.homepage,
        budget=movie.budget,
        revenue=movie.revenue,
        adult=movie.adult,
        collection=collection,
        keywords=keywords,
        cast=cast,
        crew=crew,
        directors=[member.name for member in crew if member.job in DIRECTOR_JOBS],
    )


def list_genres(session: Session) -> list[GenreOut]:
    rows = session.execute(select(Genre).order_by(Genre.name)).scalars().all()
    return [GenreOut.model_validate(row) for row in rows]


def list_languages(session: Session, limit: int = 40) -> list[dict[str, object]]:
    """Languages present in the catalog, most common first (for filter UI)."""
    rows = session.execute(
        select(
            Movie.original_language,
            func.count(distinct(Movie.tmdb_id)).label("count"),
        )
        .where(Movie.original_language.isnot(None), Movie.adult.is_(False))
        .group_by(Movie.original_language)
        .order_by(func.count(distinct(Movie.tmdb_id)).desc())
        .limit(limit)
    ).all()
    return [{"code": code, "count": int(count)} for code, count in rows]


def distinct_title_count(session: Session) -> int:
    """Distinct tmdb_ids in the catalogue (45,264 rows collapse to 44,121)."""
    return int(
        session.execute(select(func.count(distinct(Movie.tmdb_id)))).scalar_one()
    )


def year_bounds(session: Session) -> dict[str, int | None]:
    row = session.execute(
        select(func.min(Movie.release_year), func.max(Movie.release_year)).where(
            Movie.release_year.isnot(None)
        )
    ).one()
    return {"min_year": row[0], "max_year": row[1]}
