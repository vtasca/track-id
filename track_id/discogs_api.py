"""Discogs data source for music metadata enrichment."""

import requests
import time
from typing import Dict, List, Optional, Any
from .data_sources import DataSource

DISCOGS_API_BASE = "https://api.discogs.com"
USER_AGENT = "track-id/1.0.0 (https://github.com/vtasca/track-id)"


class DiscogsDataSource(DataSource):
    """Discogs data source implementation."""

    def __init__(self):
        super().__init__("Discogs")
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        })

    def _get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        time.sleep(1.5)  # Stay within 25 req/min unauthenticated limit
        response = self._session.get(url, params=params)
        if response.status_code == 200:
            return response.json()
        raise Exception(f"Discogs API error: {response.status_code} - {response.text[:200]}")

    def search(self, search_text: str) -> Dict[str, Any]:
        """Search Discogs for releases containing the track. search_text is 'artist - title'."""
        # Freetext search handles multilingual and hyphenated titles better than
        # structured artist+track params, which fail on exact-match misses.
        query = search_text.replace(" - ", " ")
        params: Dict[str, Any] = {"q": query, "type": "release", "per_page": 10}
        return self._get(f"{DISCOGS_API_BASE}/database/search", params=params)

    def find_matching_track(
        self, search_results: Dict[str, Any], artist: str, title: str
    ) -> Optional[Dict[str, Any]]:
        results = search_results.get("results", [])
        if not results:
            return None
        # Prefer releases linked to a master (more canonical umbrella release)
        with_master = [r for r in results if r.get("master_id")]
        best = with_master[0] if with_master else results[0]
        # Pass search context through so _get_detailed_track_info can match the tracklist
        return {**best, "_search_artist": artist, "_search_title": title}

    def _fetch_master(self, master_id: int) -> Dict[str, Any]:
        return self._get(f"{DISCOGS_API_BASE}/masters/{master_id}")

    def _fetch_release(self, release_id: int) -> Dict[str, Any]:
        return self._get(f"{DISCOGS_API_BASE}/releases/{release_id}")

    def _find_track_in_tracklist(
        self, tracklist: List[Dict[str, Any]], title: str
    ) -> Optional[Dict[str, Any]]:
        def normalize(s: str) -> str:
            return " ".join(s.lower().replace("-", " ").split())

        target = normalize(title)
        for track in tracklist:
            if track.get("type_", "track") != "track":
                continue
            candidate = normalize(track.get("title", ""))
            if candidate == target or target in candidate or candidate in target:
                return track
        return None

    def _get_detailed_track_info(self, track_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch master (preferred) or release, then locate the specific track in the tracklist."""
        search_title = track_data.get("_search_title", "")
        master_id = track_data.get("master_id")

        if master_id:
            detail = self._fetch_master(master_id)
            source = "master"
        else:
            detail = self._fetch_release(track_data["id"])
            source = "release"

        matched_track = self._find_track_in_tracklist(
            detail.get("tracklist", []), search_title
        )

        if matched_track is not None:
            actual_tracks = [
                t for t in detail.get("tracklist", [])
                if t.get("type_", "track") == "track"
            ]
            track_number = next(
                (i + 1 for i, t in enumerate(actual_tracks) if t is matched_track),
                None,
            )
            matched_track = {
                **matched_track,
                "_track_number": track_number,
                "_track_total": len(actual_tracks),
            }

        return {
            "_source": source,
            "_release_stub": track_data,
            "_matched_track": matched_track,
            **detail,
        }

    def extract_metadata(self, track_data: Dict[str, Any]) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {}

        # Album title
        if album := track_data.get("title"):
            metadata["TALB"] = album

        # Year
        if year := track_data.get("year"):
            metadata["TDRC"] = str(year)

        # Artists
        artists = track_data.get("artists", [])
        if artists:
            artist_str = " & ".join(
                a.get("name", "") for a in artists if a.get("name")
            )
            if artist_str:
                metadata["TPE1"] = artist_str
                metadata["TPE2"] = artist_str

        # Genre and styles — Discogs community tags, often more granular than other sources
        genres = track_data.get("genres", [])
        styles = track_data.get("styles", [])
        if genres:
            metadata["TCON"] = genres[0]
        if styles:
            metadata["TXXX:STYLE"] = ", ".join(styles)

        # Label — master doesn't carry labels; use the search result stub
        stub = track_data.get("_release_stub", {})
        stub_labels = stub.get("label", [])
        if stub_labels:
            metadata["TPUB"] = stub_labels[0] if isinstance(stub_labels, list) else stub_labels

        # Track-level fields from the matched tracklist entry
        matched = track_data.get("_matched_track")
        if matched:
            if track_title := matched.get("title"):
                metadata["TIT2"] = track_title

            num = matched.get("_track_number")
            total = matched.get("_track_total")
            if num and total:
                metadata["TRCK"] = f"{num}/{total}"
            elif num:
                metadata["TRCK"] = str(num)

        # Artwork: primary image from the master/release images array
        images = track_data.get("images", [])
        primary = next((img for img in images if img.get("type") == "primary"), None)
        img = primary or (images[0] if images else None)
        if img and (uri := img.get("uri")):
            metadata["artwork_url"] = uri

        # Discogs release page URL for reference
        uri = stub.get("uri", "")
        if uri:
            metadata["TXXX:DISCOGS_URL"] = f"https://www.discogs.com{uri}"

        return metadata
