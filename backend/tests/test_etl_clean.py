"""Task 2 acceptance tests for the ETL cleaning pipeline.

Fast tests run on tiny synthetic frames modelled on the real data's defects.
The slow end-to-end test against the real pickles is marked `slow` and is
skipped when the pickles are absent.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from etl.clean import (
    BACKEND_ROOT,
    MAX_CAST_PER_MOVIE,
    CleanReport,
    _blank_to_none,
    _extract_collections,
    _extract_credits,
    _explode_named_entities,
    _parse_dict,
    _parse_list,
    _parse_literal,
    build_catalog,
    clean_credits_frame,
    clean_keywords_frame,
    clean_links_frame,
    clean_metadata_frame,
    load_movies_frame,
)

# --------------------------------------------------------------------------- #
# literal parsing
# --------------------------------------------------------------------------- #


def test_parse_literal_handles_single_quoted_payloads() -> None:
    """The dataset uses Python repr, not JSON, so json.loads would fail here."""
    raw = "[{'id': 16, 'name': 'Animation'}, {'id': 35, 'name': 'Comedy'}]"
    assert _parse_list(raw) == [
        {"id": 16, "name": "Animation"},
        {"id": 35, "name": "Comedy"},
    ]


def test_parse_literal_handles_embedded_apostrophes() -> None:
    raw = "[{'id': 1, 'name': \"Andy's toys\"}]"
    assert _parse_list(raw) == [{"id": 1, "name": "Andy's toys"}]


def test_parse_list_returns_empty_for_empty_and_invalid() -> None:
    for value in ("[]", "", "   ", None, float("nan"), "not-a-literal", "{'a': 1}"):
        assert _parse_list(value) == []


def test_parse_dict_reads_collection_payload_and_rejects_lists() -> None:
    raw = "{'id': 10194, 'name': 'Toy Story Collection', 'poster_path': '/p.jpg'}"
    parsed = _parse_dict(raw)
    assert parsed is not None
    assert parsed["id"] == 10194
    assert _parse_dict("[{'id': 1}]") is None
    assert _parse_dict(None) is None


def test_parse_literal_does_not_execute_code() -> None:
    """literal_eval must refuse callables; a bare name is not a literal."""
    assert _parse_literal("__import__('os').system('echo hi')") is None


def test_blank_to_none_normalises_sentinels() -> None:
    series = pd.Series(["ok", "", "   ", None, np.nan, "nan", "None"])
    result = _blank_to_none(series).tolist()
    assert result == ["ok", None, None, None, None, None, None]


# --------------------------------------------------------------------------- #
# canonical catalog invariants
# --------------------------------------------------------------------------- #


def _synthetic_movies() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": [862, 105045, 105045, 8844],
            "imdb_id": ["tt0114709", "tt1", "tt1", "tt0113497"],
            "title": ["Toy Story", "The Promise", "The Promise", "Jumanji"],
            "tags": ["woody andy toy", "promise", "promise", "jungle board game"],
            "poster_path": ["/a.jpg", "/b.jpg", "/b.jpg", "/c.jpg"],
        }
    )


def test_load_movies_adds_row_index_without_reordering() -> None:
    movies = load_movies_frame(_synthetic_movies())
    assert movies["row_index"].tolist() == [0, 1, 2, 3]
    assert movies["title"].tolist() == ["Toy Story", "The Promise", "The Promise", "Jumanji"]
    assert movies["tmdb_id"].tolist() == [862, 105045, 105045, 8844]


def test_load_movies_rejects_non_contiguous_index() -> None:
    """Row order is the only link to vectors.pkl, so a broken index must fail loudly."""
    broken = _synthetic_movies()
    broken.index = [0, 1, 5, 9]
    with pytest.raises(ValueError, match="RangeIndex"):
        load_movies_frame(broken)


def test_duplicate_tmdb_ids_are_preserved_not_dropped() -> None:
    """movies.pkl is user-curated and immutable: duplicates must survive."""
    movies = load_movies_frame(_synthetic_movies())
    assert len(movies) == 4
    assert (movies["tmdb_id"] == 105045).sum() == 2
    assert movies["row_index"].is_unique


# --------------------------------------------------------------------------- #
# metadata cleaning
# --------------------------------------------------------------------------- #


def _synthetic_metadata() -> pd.DataFrame:
    """Includes a shifted/malformed row and a duplicate id, like the real file."""
    base = {
        "adult": "False",
        "belongs_to_collection": None,
        "budget": "0",
        "genres": "[]",
        "homepage": None,
        "imdb_id": "tt0000000",
        "original_language": "en",
        "original_title": "T",
        "overview": "An overview.",
        "popularity": "1.5",
        "poster_path": "/p.jpg",
        "production_companies": "[]",
        "production_countries": "[]",
        "release_date": "1995-10-30",
        "revenue": 0.0,
        "runtime": 100.0,
        "spoken_languages": "[]",
        "status": "Released",
        "tagline": None,
        "title": "T",
        "video": False,
        "vote_average": 7.0,
        "vote_count": 100.0,
    }
    rows = [
        {**base, "id": "862", "title": "Toy Story",
         "genres": "[{'id': 16, 'name': 'Animation'}]",
         "belongs_to_collection": "{'id': 10194, 'name': 'Toy Story Collection'}"},
        # duplicate id -> second occurrence dropped
        {**base, "id": "862", "title": "Toy Story DUPLICATE"},
        # malformed: shifted columns put a date where `adult` should be
        {**base, "id": "105045", "adult": "1997-08-20", "budget": "1997-08-20"},
        # runtime 0 means unknown, not a zero-length film
        {**base, "id": "8844", "title": "Jumanji", "runtime": 0.0, "adult": "True"},
        {**base, "id": "9999", "title": "Blankish", "overview": "  "},
    ]
    return pd.DataFrame(rows)


def test_clean_metadata_drops_malformed_and_duplicate_rows() -> None:
    report = CleanReport()
    cleaned = clean_metadata_frame(_synthetic_metadata(), report)

    assert report.metadata_rows_in == 5
    assert report.metadata_malformed_dropped == 1
    assert report.metadata_duplicate_ids_dropped == 1
    assert report.metadata_rows_out == 3
    assert 105045 not in cleaned["tmdb_id"].tolist()
    assert cleaned["tmdb_id"].is_unique
    # first occurrence wins
    assert cleaned.loc[cleaned["tmdb_id"] == 862, "title"].iloc[0] == "Toy Story"


def test_clean_metadata_types_and_sentinels() -> None:
    cleaned = clean_metadata_frame(_synthetic_metadata(), CleanReport()).set_index("tmdb_id")

    assert cleaned.loc[862, "release_year"] == 1995
    assert pd.api.types.is_datetime64_any_dtype(cleaned["release_date"])
    # runtime 0 becomes NaN (unknown), not 0
    assert pd.isna(cleaned.loc[8844, "runtime"])
    assert cleaned.loc[862, "runtime"] == 100.0
    # whitespace-only overview becomes None
    assert cleaned.loc[9999, "overview"] is None
    # adult coerced to real bool
    assert cleaned["adult"].dtype == bool
    assert bool(cleaned.loc[8844, "adult"]) is True
    assert bool(cleaned.loc[862, "adult"]) is False


def test_clean_metadata_parses_nested_columns() -> None:
    cleaned = clean_metadata_frame(_synthetic_metadata(), CleanReport()).set_index("tmdb_id")
    assert cleaned.loc[862, "genres_parsed"] == [{"id": 16, "name": "Animation"}]
    assert cleaned.loc[862, "collection_parsed"]["id"] == 10194
    assert cleaned.loc[8844, "genres_parsed"] == []


# --------------------------------------------------------------------------- #
# relation extraction
# --------------------------------------------------------------------------- #


def test_explode_named_entities_builds_dimension_and_bridge() -> None:
    frame = pd.DataFrame(
        {
            "tmdb_id": [1, 2, 3],
            "items": [
                [{"id": 16, "name": "Animation"}, {"id": 35, "name": "Comedy"}],
                [{"id": 35, "name": "Comedy"}, {"id": 35, "name": "Comedy"}],
                [],
            ],
        }
    )
    dim, bridge = _explode_named_entities(frame, "items", {1, 2, 3})
    assert dim["id"].tolist() == [16, 35]
    # duplicate entity within one movie collapses to a single bridge row
    assert len(bridge) == 3
    assert sorted(map(tuple, bridge.to_numpy().tolist())) == [(1, 16), (1, 35), (2, 35)]


def test_explode_named_entities_ignores_unwanted_ids() -> None:
    frame = pd.DataFrame({"tmdb_id": [1, 99], "items": [[{"id": 1, "name": "A"}]] * 2})
    _, bridge = _explode_named_entities(frame, "items", {1})
    assert bridge["tmdb_id"].tolist() == [1]


def test_extract_credits_caps_cast_and_keeps_key_crew() -> None:
    cast = [
        {"id": 100 + i, "name": f"Actor {i}", "character": f"Role {i}", "order": i}
        for i in range(25)
    ]
    crew = [
        {"id": 7879, "name": "John Lasseter", "job": "Director", "department": "Directing"},
        {"id": 7879, "name": "John Lasseter", "job": "Director", "department": "Directing"},
        {"id": 900, "name": "Writer Person", "job": "Screenplay", "department": "Writing"},
        {"id": 901, "name": "Grip Person", "job": "Grip", "department": "Crew"},
    ]
    frame = pd.DataFrame(
        {"tmdb_id": [862], "cast_parsed": [cast], "crew_parsed": [crew]}
    )
    people, credits = _extract_credits(frame, {862})

    cast_rows = credits[credits["credit_type"] == "cast"]
    crew_rows = credits[credits["credit_type"] == "crew"]

    assert len(cast_rows) == MAX_CAST_PER_MOVIE
    assert cast_rows["billing_order"].tolist() == list(range(MAX_CAST_PER_MOVIE))
    # repeated identical crew credit deduped; unwanted job "Grip" excluded
    assert sorted(crew_rows["role"].tolist()) == ["Director", "Screenplay"]
    assert 901 not in people["id"].tolist()
    assert people["id"].is_unique


def test_extract_credits_handles_missing_order_field() -> None:
    cast = [{"id": 1, "name": "A", "character": "X"}]
    frame = pd.DataFrame({"tmdb_id": [5], "cast_parsed": [cast], "crew_parsed": [[]]})
    _, credits = _extract_credits(frame, {5})
    assert credits["billing_order"].tolist() == [None]


def test_extract_collections_builds_dimension_and_mapping() -> None:
    metadata = pd.DataFrame(
        {
            "tmdb_id": [862, 863, 8844],
            "collection_parsed": [
                {"id": 10194, "name": "Toy Story Collection", "poster_path": "/p.jpg"},
                {"id": 10194, "name": "Toy Story Collection"},
                None,
            ],
        }
    )
    collections, mapping = _extract_collections(metadata)
    assert collections["id"].tolist() == [10194]
    assert mapping[862] == 10194 and mapping[863] == 10194
    assert 8844 not in mapping.index


# --------------------------------------------------------------------------- #
# supporting frames
# --------------------------------------------------------------------------- #


def test_clean_links_drops_null_tmdb_and_casts_int() -> None:
    report = CleanReport()
    links = clean_links_frame(
        pd.DataFrame(
            {
                "movieId": [1, 2, 3, 4],
                "imdbId": [114709, 113497, 1, 2],
                "tmdbId": [862.0, 8844.0, np.nan, 862.0],
            }
        ),
        report,
    )
    assert report.links_null_tmdb_dropped == 1
    assert links["tmdb_id"].tolist() == [862, 8844]  # duplicate 862 dropped
    assert links["tmdb_id"].dtype == np.int64


def test_clean_keywords_and_credits_dedupe_by_id() -> None:
    kw_report = CleanReport()
    keywords = clean_keywords_frame(
        pd.DataFrame(
            {"id": [862, 862], "keywords": ["[{'id': 931, 'name': 'jealousy'}]", "[]"]}
        ),
        kw_report,
    )
    assert kw_report.keywords_duplicate_ids_dropped == 1
    assert keywords["keywords_parsed"].iloc[0] == [{"id": 931, "name": "jealousy"}]

    cr_report = CleanReport()
    credits = clean_credits_frame(
        pd.DataFrame({"id": [862, 862], "cast": ["[]", "[]"], "crew": ["[]", "[]"]}),
        cr_report,
    )
    assert cr_report.credits_duplicate_ids_dropped == 1
    assert len(credits) == 1


# --------------------------------------------------------------------------- #
# end-to-end against the real pickles
# --------------------------------------------------------------------------- #

_REAL_PICKLES = [
    BACKEND_ROOT / name
    for name in ("movies.pkl", "movies_metadata.pkl", "credits.pkl", "keywords.pkl", "links.pkl")
]

requires_pickles = pytest.mark.skipif(
    not all(path.exists() for path in _REAL_PICKLES),
    reason="raw dataset pickles not present",
)


@pytest.fixture(scope="module")
def real_catalog():
    return build_catalog()


@requires_pickles
def test_join_preserves_movies_pkl_row_order_exactly(real_catalog) -> None:  # noqa: ANN001
    """The single most important invariant: vectors.pkl alignment.

    Row i of the output must be row i of movies.pkl, with the same title and id.
    """
    source = pd.read_pickle(BACKEND_ROOT / "movies.pkl")
    result = real_catalog.movies

    assert len(result) == len(source)
    assert result["row_index"].tolist() == list(range(len(source)))
    assert result["tmdb_id"].to_numpy().tolist() == source["id"].to_numpy().tolist()
    assert result["title"].astype(object).tolist() == source["title"].tolist()
    assert result["poster_path"].tolist() == source["poster_path"].tolist()


@requires_pickles
def test_real_catalog_keys_and_counts(real_catalog) -> None:  # noqa: ANN001
    movies = real_catalog.movies
    report = real_catalog.report

    # row_index is the primary key; tmdb_id deliberately is not unique.
    assert movies["row_index"].is_unique
    assert not movies["tmdb_id"].is_unique
    assert report.movies_rows == 45_264
    assert report.movies_distinct_ids == 44_121

    # The three known shifted rows in the Kaggle file, and its ~30 duplicate ids.
    assert report.metadata_malformed_dropped == 3
    assert report.metadata_duplicate_ids_dropped == 30


@requires_pickles
def test_real_catalog_relations_reference_known_movies(real_catalog) -> None:  # noqa: ANN001
    known_ids = set(real_catalog.movies["tmdb_id"].tolist())
    for name in ("movie_genres", "movie_keywords", "credits", "links"):
        frame = getattr(real_catalog, name)
        assert set(frame["tmdb_id"]).issubset(known_ids), f"{name} references unknown movies"

    # Relations are keyed by tmdb_id, so they must not be inflated by the
    # 1,142 duplicate catalog rows.
    assert real_catalog.credits["tmdb_id"].nunique() <= 44_121


@requires_pickles
def test_real_catalog_spot_check_toy_story(real_catalog) -> None:  # noqa: ANN001
    movies = real_catalog.movies
    toy_story = movies[movies["tmdb_id"] == 862].iloc[0]
    assert toy_story["title"] == "Toy Story"
    assert toy_story["release_year"] == 1995
    assert toy_story["runtime"] == 81.0
    assert bool(toy_story["adult"]) is False

    genre_ids = real_catalog.movie_genres.loc[
        real_catalog.movie_genres["tmdb_id"] == 862, "genre_id"
    ].tolist()
    genre_names = set(
        real_catalog.genres[real_catalog.genres["id"].isin(genre_ids)]["name"].tolist()
    )
    assert {"Animation", "Comedy", "Family"} <= genre_names

    credits = real_catalog.credits
    directors = credits[(credits["tmdb_id"] == 862) & (credits["role"] == "Director")]
    director_names = set(
        real_catalog.people[real_catalog.people["id"].isin(directors["person_id"])]["name"]
    )
    assert "John Lasseter" in director_names

    top_billed = credits[
        (credits["tmdb_id"] == 862) & (credits["credit_type"] == "cast")
    ].sort_values("billing_order")
    lead_id = top_billed.iloc[0]["person_id"]
    lead_name = real_catalog.people.loc[
        real_catalog.people["id"] == lead_id, "name"
    ].iloc[0]
    assert lead_name == "Tom Hanks"


@requires_pickles
def test_real_catalog_cast_cap_respected(real_catalog) -> None:  # noqa: ANN001
    cast = real_catalog.credits[real_catalog.credits["credit_type"] == "cast"]
    per_movie = cast.groupby("tmdb_id").size()
    assert per_movie.max() <= MAX_CAST_PER_MOVIE
