"""Task 8 acceptance tests: TMDB media resolution.

All TMDB traffic is mocked. These tests must never touch the network, so they
run identically with or without a configured API key.
"""

from __future__ import annotations

from typing import Any

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from etl.clean import CleanReport, CleanedData
from etl.seed import seed
from vaultstream.config import get_settings
from vaultstream.models.media import (
    RESOLUTION_ERROR,
    RESOLUTION_NOT_FOUND,
    RESOLUTION_OK,
    MovieMedia,
)
from vaultstream.services import media as media_service
from vaultstream.services.tmdb import (
    MediaPayload,
    TMDBAuthError,
    parse_media_payload,
    select_trailer,
)
from vaultstream.services import tmdb as tmdb_service


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _minimal_catalog() -> CleanedData:
    movies = pd.DataFrame(
        {
            "row_index": [0, 1, 2],
            "tmdb_id": [862, 8844, 999999],
            "title": ["Toy Story", "Jumanji", "Ghost Title"],
            "original_title": ["Toy Story", "Jumanji", "Ghost Title"],
            "imdb_id": ["tt0114709", "tt0113497", None],
            "tags": ["a", "b", "c"],
            # A stale path (as in the real data) and a null one.
            "poster_path": ["/stale-toy.jpg", None, "/ghost.jpg"],
            "backdrop_path": [None, None, None],
            "release_year": pd.array([1995, 1995, 1999], dtype="Int64"),
            "release_date": pd.to_datetime(["1995-10-30", "1995-12-15", "1999-01-01"]),
            "runtime": [81.0, 104.0, 90.0],
            "vote_average": [7.7, 6.9, 5.0],
            "vote_count": [5415.0, 2413.0, 50.0],
            "popularity": [21.9, 17.0, 1.0],
            "original_language": ["en", "en", "en"],
            "status": ["Released"] * 3,
            "tagline": [None] * 3,
            "overview": ["o"] * 3,
            "homepage": [None] * 3,
            "budget": [0.0] * 3,
            "revenue": [0.0] * 3,
            "adult": [False] * 3,
            "collection_id": pd.array([None, None, None], dtype="Int64"),
        }
    )
    empty_pairs = pd.DataFrame({"tmdb_id": pd.Series(dtype="int64"),
                                "genre_id": pd.Series(dtype="int64")})
    return CleanedData(
        movies=movies,
        genres=pd.DataFrame({"id": pd.Series(dtype="int64"), "name": pd.Series(dtype="string")}),
        movie_genres=empty_pairs,
        keywords=pd.DataFrame({"id": pd.Series(dtype="int64"), "name": pd.Series(dtype="string")}),
        movie_keywords=pd.DataFrame({"tmdb_id": pd.Series(dtype="int64"),
                                     "keyword_id": pd.Series(dtype="int64")}),
        people=pd.DataFrame({"id": pd.Series(dtype="int64"), "name": pd.Series(dtype="string"),
                             "profile_path": pd.Series(dtype="object"),
                             "gender": pd.Series(dtype="int64")}),
        credits=pd.DataFrame({"tmdb_id": pd.Series(dtype="int64"),
                              "person_id": pd.Series(dtype="int64"),
                              "credit_type": pd.Series(dtype="string"),
                              "role": pd.Series(dtype="object"),
                              "department": pd.Series(dtype="object"),
                              "billing_order": pd.Series(dtype="object")}),
        collections=pd.DataFrame({"id": pd.Series(dtype="int64"),
                                  "name": pd.Series(dtype="object"),
                                  "poster_path": pd.Series(dtype="object"),
                                  "backdrop_path": pd.Series(dtype="object")}),
        links=pd.DataFrame({"tmdb_id": pd.Series(dtype="int64"),
                            "movielens_id": pd.Series(dtype="int64"),
                            "imdb_numeric_id": pd.Series(dtype="int64")}),
        report=CleanReport(),
    )


TOY_STORY_RESPONSE: dict[str, Any] = {
    "id": 862,
    "poster_path": "/fresh-toy.jpg",
    "backdrop_path": "/fresh-toy-backdrop.jpg",
    "videos": {
        "results": [
            {
                "site": "YouTube",
                "key": "fan-upload",
                "type": "Trailer",
                "official": False,
                "name": "Fan Trailer",
                "published_at": "2020-01-01T00:00:00.000Z",
            },
            {
                "site": "YouTube",
                "key": "official-old",
                "type": "Trailer",
                "official": True,
                "name": "Official Trailer",
                "published_at": "2010-01-01T00:00:00.000Z",
            },
            {
                "site": "YouTube",
                "key": "official-new",
                "type": "Trailer",
                "official": True,
                "name": "Official Trailer (Remastered)",
                "published_at": "2019-06-01T00:00:00.000Z",
            },
            {
                "site": "Vimeo",
                "key": "vimeo-key",
                "type": "Trailer",
                "official": True,
                "name": "Vimeo",
            },
        ]
    },
}


@pytest.fixture
def seeded(db_session: Session) -> None:
    seed(db_session, _minimal_catalog(), truncate=True)
    db_session.flush()


@pytest.fixture
def tmdb_key(monkeypatch: pytest.MonkeyPatch):
    """Configure a fake key and clear the settings cache around the test."""
    monkeypatch.setenv("TMDB_API_KEY", "test-key-123")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# trailer selection
# --------------------------------------------------------------------------- #
def test_select_trailer_prefers_official_youtube_then_newest() -> None:
    chosen = select_trailer(TOY_STORY_RESPONSE["videos"]["results"])
    assert chosen is not None
    # Official beats the newer fan upload; among officials the newest wins.
    assert chosen["key"] == "official-new"


def test_select_trailer_ignores_non_youtube_sites() -> None:
    chosen = select_trailer(
        [{"site": "Vimeo", "key": "v", "type": "Trailer", "official": True}]
    )
    assert chosen is None


def test_select_trailer_falls_back_through_type_priority() -> None:
    chosen = select_trailer(
        [
            {"site": "YouTube", "key": "clip", "type": "Clip", "official": True},
            {"site": "YouTube", "key": "teaser", "type": "Teaser", "official": True},
        ]
    )
    assert chosen is not None
    assert chosen["key"] == "teaser"  # Teaser outranks Clip


def test_select_trailer_returns_none_for_empty_and_junk() -> None:
    assert select_trailer([]) is None
    assert select_trailer([{"site": "YouTube", "type": "Trailer"}]) is None  # no key
    assert select_trailer(["not-a-dict"]) is None  # type: ignore[list-item]
    assert select_trailer([{"site": "YouTube", "key": "x", "type": "Bloopers"}]) is None


def test_parse_media_payload_extracts_artwork_and_trailer() -> None:
    payload = parse_media_payload(862, TOY_STORY_RESPONSE)
    assert payload.poster_path == "/fresh-toy.jpg"
    assert payload.backdrop_path == "/fresh-toy-backdrop.jpg"
    assert payload.trailer_key == "official-new"
    assert payload.trailer_site == "YouTube"
    assert payload.ok is True


def test_parse_media_payload_tolerates_missing_fields() -> None:
    payload = parse_media_payload(1, {})
    assert payload.poster_path is None
    assert payload.trailer_key is None
    assert payload.ok is True  # absent data is not an error


# --------------------------------------------------------------------------- #
# HTTP behaviour (mocked transport)
# --------------------------------------------------------------------------- #
def _client(handler) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://api.themoviedb.org/3"
    )


def test_fetch_media_sync_success(tmdb_key: None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # base_url already carries the /3 API version prefix.
        assert request.url.path.endswith("/movie/862")
        assert request.url.params["append_to_response"] == "videos"
        return httpx.Response(200, json=TOY_STORY_RESPONSE)

    payload = tmdb_service.fetch_media_sync(862, client=_client(handler))
    assert payload.trailer_key == "official-new"


def test_fetch_media_sync_404_marks_not_found(tmdb_key: None) -> None:
    payload = tmdb_service.fetch_media_sync(
        999999,
        client=_client(lambda request: httpx.Response(404, json={"success": False})),
    )
    assert payload.not_found is True
    assert payload.ok is False


def test_fetch_media_sync_401_raises_auth_error(tmdb_key: None) -> None:
    with pytest.raises(TMDBAuthError):
        tmdb_service.fetch_media_sync(
            862, client=_client(lambda request: httpx.Response(401, json={}))
        )


def test_fetch_media_sync_network_error_is_captured(tmdb_key: None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("boom")

    payload = tmdb_service.fetch_media_sync(862, client=_client(handler))
    assert payload.ok is False
    assert payload.error is not None
    assert "ConnectTimeout" in payload.error


def test_fetch_media_sync_without_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(tmdb_service.TMDBNotConfigured):
            tmdb_service.fetch_media_sync(862)
    finally:
        get_settings.cache_clear()


def test_v4_token_uses_bearer_header_and_v3_key_uses_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TMDB issues both credential styles; both must work."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["api_key"] = request.url.params.get("api_key")
        return httpx.Response(200, json={"id": 862})

    monkeypatch.setenv("TMDB_API_KEY", "eyJhbGciOiJIUzI1NiJ9.fake.token")
    get_settings.cache_clear()
    tmdb_service.fetch_media_sync(862, client=_client(handler))
    assert seen["auth"] == "Bearer eyJhbGciOiJIUzI1NiJ9.fake.token"
    assert seen["api_key"] is None

    monkeypatch.setenv("TMDB_API_KEY", "short_v3_key")
    get_settings.cache_clear()
    tmdb_service.fetch_media_sync(862, client=_client(handler))
    assert seen["auth"] is None
    assert seen["api_key"] == "short_v3_key"
    get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# cache storage
# --------------------------------------------------------------------------- #
def test_store_and_read_back(db_session: Session, seeded: None) -> None:
    media_service.store(
        db_session, [parse_media_payload(862, TOY_STORY_RESPONSE)]
    )
    db_session.flush()

    row = media_service.get_cached(db_session, 862)
    assert row is not None
    assert row.poster_path == "/fresh-toy.jpg"
    assert row.trailer_key == "official-new"
    assert row.resolution == RESOLUTION_OK
    assert row.has_trailer is True


def test_store_is_idempotent_and_updates(db_session: Session, seeded: None) -> None:
    media_service.store(db_session, [parse_media_payload(862, TOY_STORY_RESPONSE)])
    db_session.flush()
    media_service.store(
        db_session,
        [MediaPayload(tmdb_id=862, poster_path="/newer.jpg", trailer_key="k2")],
    )
    db_session.flush()

    rows = db_session.query(MovieMedia).filter_by(tmdb_id=862).all()
    assert len(rows) == 1
    assert rows[0].poster_path == "/newer.jpg"
    assert rows[0].trailer_key == "k2"


def test_store_records_not_found_and_error_states(
    db_session: Session, seeded: None
) -> None:
    media_service.store(
        db_session,
        [
            MediaPayload(tmdb_id=999999, not_found=True),
            MediaPayload(tmdb_id=8844, error="ConnectTimeout: boom"),
        ],
    )
    db_session.flush()

    missing = media_service.get_cached(db_session, 999999)
    failed = media_service.get_cached(db_session, 8844)
    assert missing is not None and missing.resolution == RESOLUTION_NOT_FOUND
    assert missing.not_found is True
    assert failed is not None and failed.resolution == RESOLUTION_ERROR
    assert failed.fetch_error is not None


def test_get_cached_many_batches(db_session: Session, seeded: None) -> None:
    media_service.store(
        db_session,
        [
            MediaPayload(tmdb_id=862, poster_path="/a.jpg"),
            MediaPayload(tmdb_id=8844, poster_path="/b.jpg"),
        ],
    )
    db_session.flush()

    found = media_service.get_cached_many(db_session, [862, 8844, 999999])
    assert set(found) == {862, 8844}
    assert media_service.get_cached_many(db_session, []) == {}


# --------------------------------------------------------------------------- #
# artwork preference
# --------------------------------------------------------------------------- #
def test_effective_artwork_prefers_refreshed_over_stale() -> None:
    media = MovieMedia(
        tmdb_id=862, poster_path="/fresh.jpg", backdrop_path="/fresh-bd.jpg"
    )
    poster, backdrop = media_service.effective_artwork("/stale.jpg", None, media)
    assert poster == "/fresh.jpg"
    assert backdrop == "/fresh-bd.jpg"


def test_effective_artwork_falls_back_when_unresolved() -> None:
    """Roughly a third of the stored paths still work, so keep using them."""
    poster, backdrop = media_service.effective_artwork("/stale.jpg", "/bd.jpg", None)
    assert poster == "/stale.jpg"
    assert backdrop == "/bd.jpg"


def test_effective_artwork_falls_back_when_tmdb_has_no_poster() -> None:
    media = MovieMedia(tmdb_id=1, poster_path=None, backdrop_path=None)
    poster, _ = media_service.effective_artwork("/stale.jpg", None, media)
    assert poster == "/stale.jpg"


# --------------------------------------------------------------------------- #
# resolve() and endpoints
# --------------------------------------------------------------------------- #
def test_resolve_returns_none_without_credentials(
    db_session: Session, seeded: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unconfigured TMDB must degrade, not raise."""
    monkeypatch.setenv("TMDB_API_KEY", "")
    get_settings.cache_clear()
    try:
        assert media_service.resolve(db_session, 862) is None
    finally:
        get_settings.cache_clear()


def test_resolve_uses_cache_without_fetching(
    db_session: Session, seeded: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    media_service.store(db_session, [MediaPayload(tmdb_id=862, poster_path="/c.jpg")])
    db_session.flush()

    def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("cache hit must not call TMDB")

    monkeypatch.setattr(media_service, "fetch_media_sync", explode)
    row = media_service.resolve(db_session, 862)
    assert row is not None
    assert row.poster_path == "/c.jpg"


def test_catalog_listing_serves_refreshed_poster(
    db_client: TestClient, db_session: Session, seeded: None
) -> None:
    """A refreshed path must reach the browse payload."""
    before = db_client.get("/movies", params={"include_low_quality": True}).json()
    toy_before = next(i for i in before["items"] if i["tmdb_id"] == 862)
    assert toy_before["poster_url"].endswith("/stale-toy.jpg")

    media_service.store(db_session, [MediaPayload(tmdb_id=862, poster_path="/fresh.jpg")])
    db_session.flush()

    after = db_client.get("/movies", params={"include_low_quality": True}).json()
    toy_after = next(i for i in after["items"] if i["tmdb_id"] == 862)
    assert toy_after["poster_url"].endswith("/fresh.jpg")
    assert toy_after["poster_path"] == "/fresh.jpg"


def test_stream_endpoint_returns_youtube_source(
    db_client: TestClient, db_session: Session, seeded: None
) -> None:
    media_service.store(
        db_session,
        [
            MediaPayload(
                tmdb_id=862,
                trailer_key="official-new",
                trailer_site="YouTube",
                trailer_type="Trailer",
                trailer_name="Official Trailer",
            )
        ],
    )
    db_session.flush()

    body = db_client.get("/movies/0/stream").json()
    assert body["type"] == "youtube"
    assert body["key"] == "official-new"
    assert body["title"] == "Toy Story"
    assert body["row_index"] == 0


def test_stream_endpoint_404_when_no_trailer(
    db_client: TestClient, db_session: Session, seeded: None
) -> None:
    media_service.store(db_session, [MediaPayload(tmdb_id=8844, trailer_key=None)])
    db_session.flush()

    response = db_client.get("/movies/1/stream")
    assert response.status_code == 404
    assert "No trailer" in response.json()["detail"]


def test_stream_endpoint_explains_titles_absent_from_tmdb(
    db_client: TestClient, db_session: Session, seeded: None
) -> None:
    media_service.store(db_session, [MediaPayload(tmdb_id=999999, not_found=True)])
    db_session.flush()

    response = db_client.get("/movies/2/stream")
    assert response.status_code == 404
    assert "not listed on TMDB" in response.json()["detail"]


def test_stream_endpoint_404_for_unknown_movie(
    db_client: TestClient, seeded: None
) -> None:
    assert db_client.get("/movies/54321/stream").status_code == 404


def test_stream_endpoint_503_when_unconfigured(
    db_client: TestClient, seeded: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TMDB_API_KEY", "")
    get_settings.cache_clear()
    try:
        response = db_client.get("/movies/0/stream")
        assert response.status_code == 503
        assert "TMDB_API_KEY" in response.json()["detail"]
    finally:
        get_settings.cache_clear()


def test_detail_reports_trailer_availability(
    db_client: TestClient, db_session: Session, seeded: None
) -> None:
    assert db_client.get("/movies/0").json()["has_trailer"] is False
    media_service.store(db_session, [MediaPayload(tmdb_id=862, trailer_key="abc")])
    db_session.flush()
    assert db_client.get("/movies/0").json()["has_trailer"] is True


def test_coverage_endpoint_reports_progress(
    db_client: TestClient, db_session: Session, seeded: None
) -> None:
    media_service.store(
        db_session,
        [
            MediaPayload(tmdb_id=862, poster_path="/a.jpg", trailer_key="k"),
            MediaPayload(tmdb_id=8844, poster_path=None),
        ],
    )
    db_session.flush()

    body = db_client.get("/media/coverage").json()
    assert body["rows"] == 2
    assert body["with_poster"] == 1
    assert body["with_trailer"] == 1
    assert body["distinct_titles"] == 3
