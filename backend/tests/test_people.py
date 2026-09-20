"""Task 7 acceptance tests: filmography and collections."""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from etl.clean import CleanReport, CleanedData
from etl.seed import seed
from vaultstream.services import media as media_service
from vaultstream.services.tmdb import MediaPayload


def _catalog() -> CleanedData:
    """Two franchise entries, a standalone film, and a duplicated row.

    rows 1 and 2 share tmdb_id 863 so filmography deduplication is exercised.
    """
    rows = [
        # row_index, tmdb, title, year, collection
        (0, 862, "Toy Story", 1995, 10194),
        (1, 863, "Toy Story 2", 1999, 10194),
        (2, 863, "Toy Story 2", 1999, 10194),  # verbatim duplicate
        (3, 8844, "Jumanji", 1995, None),
    ]
    movies = pd.DataFrame(
        {
            "row_index": [r[0] for r in rows],
            "tmdb_id": [r[1] for r in rows],
            "title": [r[2] for r in rows],
            "original_title": [r[2] for r in rows],
            "release_year": pd.array([r[3] for r in rows], dtype="Int64"),
            "release_date": pd.to_datetime([f"{r[3]}-06-01" for r in rows]),
            "collection_id": pd.array([r[4] for r in rows], dtype="Int64"),
            "imdb_id": [f"tt{r[1]:07d}" for r in rows],
            "tags": ["t"] * len(rows),
            "poster_path": ["/stale.jpg"] * len(rows),
            "backdrop_path": [None] * len(rows),
            "runtime": [90.0] * len(rows),
            "vote_average": [7.5, 7.0, 7.0, 6.9],
            "vote_count": [1000.0] * len(rows),
            "popularity": [10.0] * len(rows),
            "original_language": ["en"] * len(rows),
            "status": ["Released"] * len(rows),
            "tagline": [None] * len(rows),
            "overview": ["o"] * len(rows),
            "homepage": [None] * len(rows),
            "budget": [0.0] * len(rows),
            "revenue": [0.0] * len(rows),
            "adult": [False] * len(rows),
        }
    )
    return CleanedData(
        movies=movies,
        genres=pd.DataFrame({"id": [16], "name": ["Animation"]}),
        movie_genres=pd.DataFrame({"tmdb_id": [862, 863], "genre_id": [16, 16]}),
        keywords=pd.DataFrame({"id": pd.Series(dtype="int64"), "name": pd.Series(dtype="string")}),
        movie_keywords=pd.DataFrame(
            {"tmdb_id": pd.Series(dtype="int64"), "keyword_id": pd.Series(dtype="int64")}
        ),
        people=pd.DataFrame(
            {
                "id": [31, 7879, 404404],
                "name": ["Tom Hanks", "John Lasseter", "Nobody At All"],
                "profile_path": ["/th.jpg", None, None],
                "gender": [2, 2, 0],
            }
        ),
        credits=pd.DataFrame(
            {
                # Tom Hanks acts in both Toy Story films; Lasseter directs one
                # and also has a writing credit on it.
                "tmdb_id": [862, 863, 862, 862],
                "person_id": [31, 31, 7879, 7879],
                "credit_type": ["cast", "cast", "crew", "crew"],
                "role": ["Woody", "Woody", "Director", "Screenplay"],
                "department": [None, None, "Directing", "Writing"],
                "billing_order": [0.0, 0.0, None, None],
            }
        ),
        collections=pd.DataFrame(
            {
                "id": [10194],
                "name": ["Toy Story Collection"],
                "poster_path": ["/tsc.jpg"],
                "backdrop_path": ["/tsb.jpg"],
            }
        ),
        links=pd.DataFrame(
            {"tmdb_id": pd.Series(dtype="int64"), "movielens_id": pd.Series(dtype="int64"),
             "imdb_numeric_id": pd.Series(dtype="int64")}
        ),
        report=CleanReport(),
    )


@pytest.fixture
def api(db_client: TestClient, db_session: Session) -> TestClient:
    seed(db_session, _catalog(), truncate=True)
    db_session.flush()
    return db_client


# --------------------------------------------------------------------------- #
# people
# --------------------------------------------------------------------------- #
def test_person_returns_filmography_split_by_credit_type(api: TestClient) -> None:
    body = api.get("/people/31").json()

    assert body["id"] == 31
    assert body["name"] == "Tom Hanks"
    assert body["gender"] == "Male"
    assert body["known_for"] == "Acting"
    assert body["cast_count"] == 2
    assert body["crew_count"] == 0
    assert {credit["title"] for credit in body["cast_credits"]} == {
        "Toy Story",
        "Toy Story 2",
    }
    assert all(credit["role"] == "Woody" for credit in body["cast_credits"])


def test_person_filmography_is_newest_first(api: TestClient) -> None:
    credits = api.get("/people/31").json()["cast_credits"]
    years = [credit["release_year"] for credit in credits]
    assert years == sorted(years, reverse=True)


def test_person_filmography_deduplicates_repeated_catalog_rows(api: TestClient) -> None:
    """rows 1 and 2 are the same film; it must appear once, at the lower row."""
    credits = api.get("/people/31").json()["cast_credits"]
    toy_story_2 = [c for c in credits if c["title"] == "Toy Story 2"]
    assert len(toy_story_2) == 1
    assert toy_story_2[0]["row_index"] == 1


def test_person_crew_credits_include_each_distinct_job(api: TestClient) -> None:
    body = api.get("/people/7879").json()
    assert body["cast_count"] == 0
    assert body["crew_count"] == 2
    assert sorted(c["role"] for c in body["crew_credits"]) == ["Director", "Screenplay"]
    # Most frequent department wins; Directing and Writing tie at 1 each, so
    # simply assert it is one of them rather than an arbitrary winner.
    assert body["known_for"] in {"Directing", "Writing"}


def test_person_with_no_credits_still_resolves(api: TestClient) -> None:
    body = api.get("/people/404404").json()
    assert body["name"] == "Nobody At All"
    assert body["cast_count"] == 0
    assert body["crew_count"] == 0
    assert body["known_for"] is None
    assert body["gender"] is None  # gender 0 maps to unknown, not a label


def test_person_credit_uses_refreshed_artwork(
    api: TestClient, db_session: Session
) -> None:
    media_service.store(db_session, [MediaPayload(tmdb_id=862, poster_path="/fresh.jpg")])
    db_session.flush()

    credits = api.get("/people/31").json()["cast_credits"]
    toy_story = next(c for c in credits if c["title"] == "Toy Story")
    assert toy_story["poster_url"].endswith("/fresh.jpg")


def test_person_limit_is_respected(api: TestClient) -> None:
    body = api.get("/people/31", params={"limit": 1}).json()
    assert body["cast_count"] + body["crew_count"] == 1


def test_unknown_person_is_404(api: TestClient) -> None:
    response = api.get("/people/999999")
    assert response.status_code == 404
    assert "999999" in response.json()["detail"]


def test_negative_person_id_is_422(api: TestClient) -> None:
    assert api.get("/people/-5").status_code == 422


# --------------------------------------------------------------------------- #
# collections
# --------------------------------------------------------------------------- #
def test_collection_returns_titles_in_release_order(api: TestClient) -> None:
    body = api.get("/collections/10194").json()

    assert body["name"] == "Toy Story Collection"
    assert body["poster_url"].endswith("/tsc.jpg")
    titles = [movie["title"] for movie in body["movies"]]
    assert titles == ["Toy Story", "Toy Story 2"]  # ascending by release date


def test_collection_deduplicates_repeated_rows(api: TestClient) -> None:
    movies = api.get("/collections/10194").json()["movies"]
    assert len(movies) == 2  # not 3, despite the duplicated row
    assert [m["row_index"] for m in movies] == [0, 1]


def test_unknown_collection_is_404(api: TestClient) -> None:
    assert api.get("/collections/424242").status_code == 404


def test_collection_siblings_excludes_the_requested_title(api: TestClient) -> None:
    siblings = api.get("/movies/0/collection").json()
    assert [movie["title"] for movie in siblings] == ["Toy Story 2"]


def test_collection_siblings_empty_for_standalone_film(api: TestClient) -> None:
    """Only ~10% of the catalogue is in a collection, so this is the common case."""
    assert api.get("/movies/3/collection").json() == []


def test_collection_siblings_empty_for_unknown_row(api: TestClient) -> None:
    assert api.get("/movies/999999/collection").json() == []
