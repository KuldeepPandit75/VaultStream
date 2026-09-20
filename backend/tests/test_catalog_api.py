"""Task 4 acceptance tests for the catalog API.

Runs against the disposable test database seeded with a small fixture catalog
built to exercise every filter, the quality floor, and tmdb_id deduplication.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from etl.clean import CleanReport, CleanedData
from etl.seed import seed
from vaultstream.services.images import backdrop_url, imdb_url, poster_url


def _fixture_catalog() -> CleanedData:
    """A 10-row catalog covering every filter dimension.

    row 3 and row 4 are the same tmdb_id (duplicate rows, as in the real
    catalog) and must collapse to one result.
    row 5 has no poster and row 6 has too few votes: both fail the quality floor.
    row 7 is adult. row 8 has no genres. row 9 is low-rated.
    """
    rows = [
        # row_index, tmdb, title, year, rating, votes, pop, lang, poster, adult
        (0, 862, "Toy Story", 1995, 7.7, 5415, 21.9, "en", "/ts.jpg", False),
        (1, 8844, "Jumanji", 1995, 6.9, 2413, 17.0, "en", "/ju.jpg", False),
        (2, 129, "Spirited Away", 2001, 8.3, 3840, 41.0, "ja", "/sa.jpg", False),
        (3, 105045, "The Promise", 1995, 5.5, 40, 1.2, "en", "/pr.jpg", False),
        (4, 105045, "The Promise", 1995, 5.5, 40, 1.2, "en", "/pr.jpg", False),
        (5, 555, "No Poster Film", 2010, 7.0, 900, 5.0, "en", None, False),
        (6, 666, "Obscure Film", 1988, 9.5, 3, 0.1, "fr", "/ob.jpg", False),
        (7, 777, "Adult Film", 2015, 6.0, 500, 3.0, "en", "/ad.jpg", True),
        (8, 888, "Genreless", 1979, 6.5, 120, 2.0, "de", "/gl.jpg", False),
        (9, 999, "Bad Movie", 2020, 2.1, 800, 4.0, "en", "/bm.jpg", False),
    ]
    movies = pd.DataFrame(
        {
            "row_index": [r[0] for r in rows],
            "tmdb_id": [r[1] for r in rows],
            "title": [r[2] for r in rows],
            "original_title": [r[2] for r in rows],
            "release_year": pd.array([r[3] for r in rows], dtype="Int64"),
            "vote_average": [r[4] for r in rows],
            "vote_count": [float(r[5]) for r in rows],
            "popularity": [r[6] for r in rows],
            "original_language": [r[7] for r in rows],
            "poster_path": [r[8] for r in rows],
            "adult": [r[9] for r in rows],
            "imdb_id": [f"tt{r[1]:07d}" for r in rows],
            "tags": ["tag"] * len(rows),
            "tagline": [None] * len(rows),
            "overview": ["An overview."] * len(rows),
            "release_date": pd.to_datetime([f"{r[3]}-01-01" for r in rows]),
            "runtime": [100.0] * len(rows),
            "budget": [0.0] * len(rows),
            "revenue": [0.0] * len(rows),
            "status": ["Released"] * len(rows),
            "homepage": [None] * len(rows),
            "collection_id": pd.array(
                [10194] + [None] * (len(rows) - 1), dtype="Int64"
            ),
            "backdrop_path": [None] * len(rows),
        }
    )
    return CleanedData(
        movies=movies,
        genres=pd.DataFrame(
            {"id": [16, 35, 10751, 12, 18], "name": ["Animation", "Comedy", "Family", "Adventure", "Drama"]}
        ),
        movie_genres=pd.DataFrame(
            {
                "tmdb_id": [862, 862, 862, 8844, 129, 129, 105045, 999],
                "genre_id": [16, 35, 10751, 12, 16, 10751, 18, 18],
            }
        ),
        keywords=pd.DataFrame({"id": [931, 4290], "name": ["jealousy", "toy"]}),
        movie_keywords=pd.DataFrame({"tmdb_id": [862, 862], "keyword_id": [931, 4290]}),
        people=pd.DataFrame(
            {
                "id": [31, 7879, 608],
                "name": ["Tom Hanks", "John Lasseter", "Hayao Miyazaki"],
                "profile_path": ["/th.jpg", None, "/hm.jpg"],
                "gender": [2, 2, 2],
            }
        ),
        credits=pd.DataFrame(
            {
                "tmdb_id": [862, 862, 862, 129],
                "person_id": [31, 7879, 7879, 608],
                "credit_type": ["cast", "crew", "crew", "crew"],
                "role": ["Woody (voice)", "Director", "Screenplay", "Director"],
                "department": [None, "Directing", "Writing", "Directing"],
                "billing_order": [0.0, None, None, None],
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
            {"tmdb_id": [862], "movielens_id": [1], "imdb_numeric_id": [114709]}
        ),
        report=CleanReport(),
    )


@pytest.fixture
def api(db_client: TestClient, db_session: Session) -> TestClient:
    seed(db_session, _fixture_catalog(), truncate=True)
    db_session.flush()
    return db_client


def _titles(payload: dict) -> list[str]:
    return [item["title"] for item in payload["items"]]


# --------------------------------------------------------------------------- #
# quality floor + dedup
# --------------------------------------------------------------------------- #
def test_default_listing_applies_quality_floor(api: TestClient) -> None:
    """Adult, poster-less, and barely-voted titles stay off browse surfaces."""
    body = api.get("/movies").json()
    titles = _titles(body)

    assert "Adult Film" not in titles
    assert "No Poster Film" not in titles
    assert "Obscure Film" not in titles
    assert "Toy Story" in titles


def test_include_low_quality_and_adult_flags_widen_results(api: TestClient) -> None:
    body = api.get("/movies", params={"include_low_quality": True}).json()
    titles = _titles(body)
    assert "No Poster Film" in titles
    assert "Obscure Film" in titles
    assert "Adult Film" not in titles  # still excluded without include_adult

    body = api.get(
        "/movies", params={"include_low_quality": True, "include_adult": True}
    ).json()
    assert "Adult Film" in _titles(body)


def test_duplicate_tmdb_ids_collapse_to_one_result(api: TestClient) -> None:
    """rows 3 and 4 share tmdb_id 105045 and must appear once."""
    body = api.get(
        "/movies", params={"q": "Promise", "include_low_quality": True}
    ).json()
    promises = [item for item in body["items"] if item["title"] == "The Promise"]
    assert len(promises) == 1
    assert promises[0]["row_index"] == 3  # lowest row_index wins
    assert body["total"] == 1


# --------------------------------------------------------------------------- #
# pagination
# --------------------------------------------------------------------------- #
def test_pagination_envelope_and_boundaries(api: TestClient) -> None:
    first = api.get("/movies", params={"page_size": 2, "page": 1}).json()
    assert first["page"] == 1
    assert first["page_size"] == 2
    assert len(first["items"]) == 2
    assert first["has_prev"] is False
    assert first["has_next"] is True
    assert first["total_pages"] == (first["total"] + 1) // 2

    second = api.get("/movies", params={"page_size": 2, "page": 2}).json()
    assert second["has_prev"] is True
    # No overlap between consecutive pages.
    assert not set(_titles(first)) & set(_titles(second))


def test_page_beyond_end_returns_empty_not_error(api: TestClient) -> None:
    response = api.get("/movies", params={"page": 9999})
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_page_size_is_capped(api: TestClient) -> None:
    body = api.get("/movies", params={"page_size": 100000}).json()
    assert body["page_size"] == 100  # settings.max_page_size


def test_page_size_zero_is_rejected(api: TestClient) -> None:
    assert api.get("/movies", params={"page_size": 0}).status_code == 422
    assert api.get("/movies", params={"page": 0}).status_code == 422


def test_pagination_is_stable_across_pages(api: TestClient) -> None:
    """A stable tiebreaker must prevent rows repeating or vanishing."""
    seen: list[str] = []
    for page in range(1, 6):
        body = api.get(
            "/movies", params={"page_size": 2, "page": page, "include_low_quality": True}
        ).json()
        seen.extend(item["row_index"] for item in body["items"])
    assert len(seen) == len(set(seen))


# --------------------------------------------------------------------------- #
# search
# --------------------------------------------------------------------------- #
def test_search_is_case_insensitive_substring(api: TestClient) -> None:
    for query in ("toy", "TOY", "oy Sto"):
        titles = _titles(api.get("/movies", params={"q": query}).json())
        assert "Toy Story" in titles, query


def test_search_with_no_match_returns_empty_page(api: TestClient) -> None:
    body = api.get("/movies", params={"q": "zzzznotathing"}).json()
    assert body["total"] == 0
    assert body["items"] == []
    assert body["total_pages"] == 0
    assert body["has_next"] is False


def test_search_does_not_leak_adult_titles(api: TestClient) -> None:
    body = api.get("/movies", params={"q": "Adult"}).json()
    assert body["items"] == []


# --------------------------------------------------------------------------- #
# filters
# --------------------------------------------------------------------------- #
def test_genre_filter_or_semantics(api: TestClient) -> None:
    body = api.get("/movies", params={"genre": ["Adventure", "Comedy"]}).json()
    assert set(_titles(body)) == {"Toy Story", "Jumanji"}


def test_genre_filter_match_all_semantics(api: TestClient) -> None:
    body = api.get(
        "/movies", params={"genre": ["Animation", "Family"], "genre_match_all": True}
    ).json()
    assert set(_titles(body)) == {"Toy Story", "Spirited Away"}


def test_genre_filter_accepts_ids_and_is_case_insensitive(api: TestClient) -> None:
    by_id = _titles(api.get("/movies", params={"genre": ["12"]}).json())
    by_name = _titles(api.get("/movies", params={"genre": ["adventure"]}).json())
    assert by_id == by_name == ["Jumanji"]


def test_unknown_genre_returns_empty_not_error(api: TestClient) -> None:
    """Regression: an unmatched genre name previously raised a 500."""
    response = api.get("/movies", params={"genre": ["NotARealGenre"]})
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_year_range_filter(api: TestClient) -> None:
    body = api.get("/movies", params={"year_from": 1995, "year_to": 1995}).json()
    # The Promise (40 votes) clears the floor of 10, and its duplicate collapses.
    assert set(_titles(body)) == {"Toy Story", "Jumanji", "The Promise"}
    assert body["total"] == 3

    body = api.get("/movies", params={"year_from": 2001}).json()
    assert "Spirited Away" in _titles(body)
    assert "Toy Story" not in _titles(body)


def test_inverted_year_range_is_rejected(api: TestClient) -> None:
    response = api.get("/movies", params={"year_from": 2000, "year_to": 1990})
    assert response.status_code == 422
    assert "year_from" in response.json()["detail"]


def test_language_filter_is_case_insensitive(api: TestClient) -> None:
    for value in ("ja", "JA"):
        assert _titles(api.get("/movies", params={"language": value}).json()) == [
            "Spirited Away"
        ]


def test_min_rating_filter(api: TestClient) -> None:
    titles = _titles(api.get("/movies", params={"min_rating": 8.0}).json())
    assert titles == ["Spirited Away"]
    assert "Bad Movie" not in titles


def test_min_votes_filter(api: TestClient) -> None:
    body = api.get("/movies", params={"min_votes": 3000}).json()
    assert set(_titles(body)) == {"Toy Story", "Spirited Away"}


def test_combined_filters_narrow_correctly(api: TestClient) -> None:
    body = api.get(
        "/movies",
        params={
            "genre": ["Animation"],
            "year_from": 2000,
            "min_rating": 8.0,
            "language": "ja",
        },
    ).json()
    assert _titles(body) == ["Spirited Away"]


# --------------------------------------------------------------------------- #
# sorting
# --------------------------------------------------------------------------- #
def test_sort_by_popularity_desc_is_default(api: TestClient) -> None:
    body = api.get("/movies").json()
    values = [item["popularity"] for item in body["items"]]
    assert values == sorted(values, reverse=True)


def test_sort_by_rating_and_release_date_both_directions(api: TestClient) -> None:
    asc = api.get("/movies", params={"sort": "rating", "order": "asc"}).json()
    ratings = [item["vote_average"] for item in asc["items"]]
    assert ratings == sorted(ratings)

    desc = api.get("/movies", params={"sort": "rating", "order": "desc"}).json()
    assert [item["vote_average"] for item in desc["items"]] == sorted(ratings, reverse=True)

    by_date = api.get("/movies", params={"sort": "release_date", "order": "desc"}).json()
    years = [item["release_year"] for item in by_date["items"]]
    assert years == sorted(years, reverse=True)


def test_sort_by_title_ascending(api: TestClient) -> None:
    body = api.get("/movies", params={"sort": "title", "order": "asc"}).json()
    titles = _titles(body)
    assert titles == sorted(titles)


def test_invalid_sort_field_is_rejected(api: TestClient) -> None:
    assert api.get("/movies", params={"sort": "nonsense"}).status_code == 422


# --------------------------------------------------------------------------- #
# detail
# --------------------------------------------------------------------------- #
def test_movie_detail_returns_full_aggregate(api: TestClient) -> None:
    body = api.get("/movies/0").json()

    assert body["row_index"] == 0
    assert body["tmdb_id"] == 862
    assert body["title"] == "Toy Story"
    assert body["genres"] == ["Animation", "Comedy", "Family"]
    assert body["release_date"] == "1995-01-01"
    assert body["imdb_url"] == "https://www.imdb.com/title/tt0000862/"
    assert body["poster_url"].endswith("/w500/ts.jpg")

    assert body["collection"]["name"] == "Toy Story Collection"
    assert [k["name"] for k in body["keywords"]] == ["jealousy", "toy"]

    assert len(body["cast"]) == 1
    assert body["cast"][0]["name"] == "Tom Hanks"
    assert body["cast"][0]["character"] == "Woody (voice)"
    assert body["cast"][0]["billing_order"] == 0
    assert body["cast"][0]["profile_url"].endswith("/w185/th.jpg")

    assert body["directors"] == ["John Lasseter"]


def test_movie_detail_orders_director_before_other_crew(api: TestClient) -> None:
    """Regression: crew came back alphabetically, burying the director."""
    body = api.get("/movies/0").json()
    assert body["crew"][0]["job"] == "Director"


def test_movie_detail_handles_sparse_records(api: TestClient) -> None:
    """A movie with no genres, keywords, cast or collection must still render."""
    body = api.get("/movies/8").json()
    assert body["title"] == "Genreless"
    assert body["genres"] == []
    assert body["keywords"] == []
    assert body["cast"] == []
    assert body["crew"] == []
    assert body["directors"] == []
    assert body["collection"] is None
    assert body["tagline"] is None


def test_movie_detail_is_reachable_for_low_quality_rows(api: TestClient) -> None:
    """The browse floor must not make a record unreachable by direct link."""
    assert api.get("/movies/5").json()["title"] == "No Poster Film"
    assert api.get("/movies/5").json()["poster_url"] is None


def test_movie_detail_unknown_row_index_is_404(api: TestClient) -> None:
    response = api.get("/movies/424242")
    assert response.status_code == 404
    assert "424242" in response.json()["detail"]


def test_movie_detail_rejects_negative_row_index(api: TestClient) -> None:
    assert api.get("/movies/-1").status_code == 422


# --------------------------------------------------------------------------- #
# supporting endpoints
# --------------------------------------------------------------------------- #
def test_genres_endpoint_is_alphabetical(api: TestClient) -> None:
    body = api.get("/genres").json()
    names = [genre["name"] for genre in body]
    assert names == sorted(names)
    assert "Animation" in names


def test_languages_endpoint_is_ordered_by_frequency(api: TestClient) -> None:
    body = api.get("/languages").json()
    counts = [entry["count"] for entry in body]
    assert counts == sorted(counts, reverse=True)
    assert body[0]["code"] == "en"


def test_filters_endpoint_exposes_bounds_for_the_ui(api: TestClient) -> None:
    body = api.get("/movies/filters").json()
    assert body["min_year"] == 1979
    assert body["max_year"] == 2020
    assert body["max_page_size"] == 100
    assert len(body["genres"]) == 5


# --------------------------------------------------------------------------- #
# image helpers
# --------------------------------------------------------------------------- #
def test_image_url_helpers_handle_missing_and_unslashed_paths() -> None:
    assert poster_url(None) is None
    assert backdrop_url("") is None
    assert poster_url("/a.jpg").endswith("/w500/a.jpg")
    # Tolerate a path without the leading slash rather than producing a bad URL.
    assert poster_url("a.jpg").endswith("/w500/a.jpg")
    assert imdb_url(None) is None
    assert imdb_url("tt0114709") == "https://www.imdb.com/title/tt0114709/"
