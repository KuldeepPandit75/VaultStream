/**
 * Types mirroring the FastAPI Pydantic schemas in
 * `backend/vaultstream/schemas/catalog.py`.
 *
 * Note: the public movie identifier is `row_index`, not `tmdb_id`. The curated
 * catalog contains duplicate tmdb_ids, so only row_index identifies one row.
 */

export interface MovieSummary {
  row_index: number;
  tmdb_id: number;
  title: string;
  release_year: number | null;
  runtime: number | null;
  vote_average: number | null;
  vote_count: number | null;
  popularity: number | null;
  poster_path: string | null;
  poster_url: string | null;
  backdrop_url: string | null;
  genres: string[];
}

export interface Keyword {
  id: number;
  name: string;
}

export interface Collection {
  id: number;
  name: string | null;
  poster_url: string | null;
  backdrop_url: string | null;
}

export interface CastMember {
  person_id: number;
  name: string;
  character: string | null;
  billing_order: number | null;
  profile_url: string | null;
}

export interface CrewMember {
  person_id: number;
  name: string;
  job: string;
  department: string | null;
  profile_url: string | null;
}

export interface OmdbRating {
  source: string;
  value: string;
}

export interface OmdbData {
  imdb_rating: number | null;
  imdb_votes: string | null;
  rated: string | null;
  awards: string | null;
  country: string | null;
  box_office: string | null;
  production: string | null;
  dvd: string | null;
  ratings: OmdbRating[];
  metascore: string | null;
  plot: string | null;
}

export interface MovieDetail extends MovieSummary {
  /** True when a playable trailer is known to exist for this title. */
  has_trailer: boolean;
  imdb_id: string | null;
  imdb_url: string | null;
  original_title: string | null;
  original_language: string | null;
  tagline: string | null;
  overview: string | null;
  release_date: string | null;
  status: string | null;
  homepage: string | null;
  budget: number | null;
  revenue: number | null;
  adult: boolean;
  collection: Collection | null;
  keywords: Keyword[];
  cast: CastMember[];
  crew: CrewMember[];
  directors: string[];
  omdb: OmdbData | null;
}

/** Playback descriptor. `type` exists so another driver can be added later. */
export interface StreamSource {
  row_index: number;
  tmdb_id: number;
  title: string;
  type: "youtube";
  key: string;
  name: string | null;
  video_type: string | null;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface Genre {
  id: number;
  name: string;
}

export interface LanguageCount {
  code: string;
  count: number;
}

export interface FilterBounds {
  genres: Genre[];
  languages: LanguageCount[];
  min_year: number | null;
  max_year: number | null;
  default_page_size: number;
  max_page_size: number;
  quality_floor_vote_count: number;
}

export type SortField =
  | "popularity"
  | "rating"
  | "release_date"
  | "title"
  | "vote_count";

export type SortOrder = "asc" | "desc";

export interface RecommendationRow {
  key: string;
  title: string;
  reason: string | null;
  /** False for a cold-start row, so the UI can avoid implying personalisation. */
  personalised: boolean;
  seed: MovieSummary | null;
  items: MovieSummary[];
}

export interface RecommendationFeed {
  rows: RecommendationRow[];
  has_history: boolean;
}

export interface WatchProgress {
  row_index: number;
  position_seconds: number;
  duration_seconds: number | null;
  completed: boolean;
  /** 0-100, or null when the duration is unknown. */
  percent_complete: number | null;
  updated_at: string;
  movie: MovieSummary;
}

export interface ResumePoint {
  row_index: number;
  position_seconds: number;
  completed: boolean;
}

export interface AuthUser {
  id: number;
  email: string;
  display_name: string;
  created_at: string;
  last_login_at: string | null;
}

export interface SessionResponse {
  user: AuthUser;
  access_expires_at: string;
}

export interface PersonCredit {
  row_index: number;
  tmdb_id: number;
  title: string;
  release_year: number | null;
  poster_url: string | null;
  vote_average: number | null;
  /** Character for cast credits, job title for crew credits. */
  role: string | null;
  credit_type: "cast" | "crew";
  department: string | null;
}

export interface PersonDetail {
  id: number;
  name: string;
  profile_url: string | null;
  gender: string | null;
  known_for: string | null;
  cast_count: number;
  crew_count: number;
  cast_credits: PersonCredit[];
  crew_credits: PersonCredit[];
}

export interface CollectionDetail {
  id: number;
  name: string | null;
  poster_url: string | null;
  backdrop_url: string | null;
  movies: MovieSummary[];
}

/** Browse query state, kept in the URL so pages are shareable and bookmarkable. */
export interface MovieQuery {
  q?: string;
  genre?: string[];
  genre_match_all?: boolean;
  year_from?: number;
  year_to?: number;
  language?: string;
  min_rating?: number;
  sort?: SortField;
  order?: SortOrder;
  page?: number;
  page_size?: number;
}
