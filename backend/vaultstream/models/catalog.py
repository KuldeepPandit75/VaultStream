"""Catalog schema.

Key modelling decision
----------------------
``movies.pkl`` is user-curated and immutable. It holds 45,264 rows but only
44,121 distinct TMDB ids (1,142 rows are exact duplicates), and its row order
is the alignment contract with ``vectors.pkl``.

Therefore:
  * ``Movie.row_index`` is the primary key -- literally the pickle's positional
    index, which is also the vector matrix row. This makes recommendation
    lookups exact by construction.
  * ``Movie.tmdb_id`` is indexed but NOT unique.
  * Relation tables key on ``tmdb_id`` so a duplicated catalog row does not
    multiply its cast or genres. Because ``tmdb_id`` is non-unique, those
    columns cannot carry a real foreign key to ``movies``; they are plain
    indexed integers and referential integrity is enforced by the seeder.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vaultstream.db import Base


class Collection(Base):
    """A TMDB franchise/collection, e.g. "Toy Story Collection"."""

    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str | None] = mapped_column(String(500))
    poster_path: Mapped[str | None] = mapped_column(String(255))
    backdrop_path: Mapped[str | None] = mapped_column(String(255))

    movies: Mapped[list[Movie]] = relationship(back_populates="collection")


class Genre(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    __table_args__ = (Index("ix_keywords_name", "name"),)


class Person(Base):
    __tablename__ = "people"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    profile_path: Mapped[str | None] = mapped_column(String(255))
    # TMDB convention: 0 unknown, 1 female, 2 male, 3 non-binary
    gender: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)

    __table_args__ = (Index("ix_people_name", "name"),)


class Movie(Base):
    """One row of the curated catalog. PK is the pickle/vector row index."""

    __tablename__ = "movies"

    row_index: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    imdb_id: Mapped[str | None] = mapped_column(String(20))

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    original_title: Mapped[str | None] = mapped_column(String(500))
    tagline: Mapped[str | None] = mapped_column(Text)
    overview: Mapped[str | None] = mapped_column(Text)
    # Token soup behind the recommendation vectors; kept for debugging/explainability.
    tags: Mapped[str | None] = mapped_column(Text)

    release_date: Mapped[date | None] = mapped_column(Date)
    release_year: Mapped[int | None] = mapped_column(SmallInteger)
    runtime: Mapped[int | None] = mapped_column(SmallInteger)

    vote_average: Mapped[float | None] = mapped_column(Float)
    vote_count: Mapped[int | None] = mapped_column(Integer)
    popularity: Mapped[float | None] = mapped_column(Float)

    budget: Mapped[int | None] = mapped_column(BigInteger)
    revenue: Mapped[int | None] = mapped_column(BigInteger)

    original_language: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str | None] = mapped_column(String(50))
    homepage: Mapped[str | None] = mapped_column(String(500))

    poster_path: Mapped[str | None] = mapped_column(String(255))
    # Absent from the dataset; filled by the TMDB resolver in Task 8.
    backdrop_path: Mapped[str | None] = mapped_column(String(255))

    adult: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    collection_id: Mapped[int | None] = mapped_column(
        ForeignKey("collections.id", ondelete="SET NULL")
    )
    collection: Mapped[Collection | None] = relationship(back_populates="movies")

    __table_args__ = (
        Index("ix_movies_tmdb_id", "tmdb_id"),
        Index("ix_movies_release_date", "release_date"),
        Index("ix_movies_release_year", "release_year"),
        Index("ix_movies_popularity", "popularity"),
        Index("ix_movies_vote_average", "vote_average"),
        Index("ix_movies_original_language", "original_language"),
        # Composite covering the default browse predicate + sort.
        Index("ix_movies_browse", "adult", "vote_count", "popularity"),
        # Trigram index for fuzzy title search (needs the pg_trgm extension).
        Index(
            "ix_movies_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
    )


class MovieGenre(Base):
    __tablename__ = "movie_genres"

    tmdb_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    genre_id: Mapped[int] = mapped_column(
        ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (Index("ix_movie_genres_genre_id", "genre_id"),)


class MovieKeyword(Base):
    __tablename__ = "movie_keywords"

    tmdb_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyword_id: Mapped[int] = mapped_column(
        ForeignKey("keywords.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (Index("ix_movie_keywords_keyword_id", "keyword_id"),)


class MovieCredit(Base):
    """Capped credits: top 15 billed cast plus selected crew jobs.

    A surrogate key is required because one person can legitimately hold two
    credits on the same film (two roles, or both Director and Writer).
    """

    __tablename__ = "movie_credits"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), nullable=False
    )
    # "cast" or "crew"
    credit_type: Mapped[str] = mapped_column(String(10), nullable=False)
    # character name for cast, job title for crew
    role: Mapped[str | None] = mapped_column(String(500))
    department: Mapped[str | None] = mapped_column(String(100))
    billing_order: Mapped[int | None] = mapped_column(SmallInteger)

    __table_args__ = (
        Index("ix_movie_credits_tmdb_id", "tmdb_id"),
        Index("ix_movie_credits_person_id", "person_id"),
        Index("ix_movie_credits_role", "credit_type", "role"),
    )


class MovieLink(Base):
    """MovieLens / IMDb id cross-reference."""

    __tablename__ = "movie_links"

    tmdb_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    movielens_id: Mapped[int] = mapped_column(Integer, nullable=False)
    imdb_numeric_id: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (Index("ix_movie_links_movielens_id", "movielens_id"),)
