"""Filmography and collection queries."""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from vaultstream.models.catalog import Collection, Movie, MovieCredit, Person
from vaultstream.schemas.catalog import MovieSummary
from vaultstream.schemas.people import (
    GENDER_LABELS,
    CollectionDetail,
    PersonCredit,
    PersonDetail,
)
from vaultstream.services import media as media_service
from vaultstream.services.catalog import _genre_names_for, _to_summary
from vaultstream.services.images import backdrop_url, poster_url, profile_url


def _canonical_rows() -> Select:
    """One representative row_index per tmdb_id.

    Needed because the catalogue repeats 1,142 rows verbatim; without this a
    filmography would list the same film several times.
    """
    return select(
        Movie.tmdb_id.label("tmdb_id"),
        func.min(Movie.row_index).label("row_index"),
    ).group_by(Movie.tmdb_id)


def get_person(session: Session, person_id: int, *, limit: int = 200) -> PersonDetail | None:
    """A person with their cast and crew filmography, newest first."""
    person = session.get(Person, person_id)
    if person is None:
        return None

    canonical = _canonical_rows().subquery("canonical")

    rows = session.execute(
        select(
            Movie.row_index,
            Movie.tmdb_id,
            Movie.title,
            Movie.release_year,
            Movie.release_date,
            Movie.poster_path,
            Movie.vote_average,
            MovieCredit.credit_type,
            MovieCredit.role,
            MovieCredit.department,
            MovieCredit.billing_order,
        )
        .join(canonical, canonical.c.tmdb_id == MovieCredit.tmdb_id)
        .join(Movie, Movie.row_index == canonical.c.row_index)
        .where(MovieCredit.person_id == person_id)
        .order_by(
            Movie.release_date.desc().nulls_last(),
            Movie.title.asc(),
        )
        .limit(limit)
    ).all()

    media_map = media_service.get_cached_many(session, [row.tmdb_id for row in rows])

    cast: list[PersonCredit] = []
    crew: list[PersonCredit] = []
    department_counts: dict[str, int] = {}

    for row in rows:
        media = media_map.get(row.tmdb_id)
        effective_poster, _ = media_service.effective_artwork(
            row.poster_path, None, media
        )
        credit = PersonCredit(
            row_index=row.row_index,
            tmdb_id=row.tmdb_id,
            title=row.title,
            release_year=row.release_year,
            poster_url=poster_url(effective_poster),
            vote_average=row.vote_average,
            role=row.role,
            credit_type=row.credit_type,
            department=row.department,
        )
        if row.credit_type == "cast":
            cast.append(credit)
            department_counts["Acting"] = department_counts.get("Acting", 0) + 1
        else:
            crew.append(credit)
            key = row.department or row.role or "Crew"
            department_counts[key] = department_counts.get(key, 0) + 1

    known_for = (
        max(department_counts.items(), key=lambda item: item[1])[0]
        if department_counts
        else None
    )

    return PersonDetail(
        id=person.id,
        name=person.name,
        profile_url=profile_url(person.profile_path),
        gender=GENDER_LABELS.get(person.gender),
        known_for=known_for,
        cast_count=len(cast),
        crew_count=len(crew),
        cast_credits=cast,
        crew_credits=crew,
    )


def get_collection(session: Session, collection_id: int) -> CollectionDetail | None:
    """A franchise and its titles in release order."""
    collection = session.get(Collection, collection_id)
    if collection is None:
        return None

    canonical = _canonical_rows().subquery("canonical")

    movies = list(
        session.execute(
            select(Movie)
            .join(canonical, canonical.c.row_index == Movie.row_index)
            .where(Movie.collection_id == collection_id)
            .order_by(Movie.release_date.asc().nulls_last(), Movie.title.asc())
        )
        .scalars()
        .all()
    )

    tmdb_ids = [movie.tmdb_id for movie in movies]
    genre_map = _genre_names_for(session, tmdb_ids)
    media_map = media_service.get_cached_many(session, tmdb_ids)

    return CollectionDetail(
        id=collection.id,
        name=collection.name,
        poster_url=poster_url(collection.poster_path),
        backdrop_url=backdrop_url(collection.backdrop_path),
        movies=[
            _to_summary(
                movie,
                genre_map.get(movie.tmdb_id, []),
                media_map.get(movie.tmdb_id),
            )
            for movie in movies
        ],
    )


def list_collection_siblings(
    session: Session, row_index: int
) -> list[MovieSummary]:
    """Other titles in the same franchise as the given row, excluding itself."""
    movie = session.get(Movie, row_index)
    if movie is None or movie.collection_id is None:
        return []

    detail = get_collection(session, movie.collection_id)
    if detail is None:
        return []
    return [entry for entry in detail.movies if entry.tmdb_id != movie.tmdb_id]
