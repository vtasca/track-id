# TODO

1. ✅ **Fix duplicate ID3 tag definitions** (`id3_tags.py`): `TPUB`, `TSRC`, `TSSE`, `TENC` appear twice with conflicting display names. Python silently uses the last definition, making the first dead code and the mapping incorrect.

2. ✅ **Fix MusicBrainz genre tags silently failing to write** (`musicbrainz_api.py`, `mp3_utils.py:142`): `musicbrainz_api.py` emits `TXXX:GENRE` but `mp3_utils.py` only handles the key `TXXX` (no colon). Genre from MusicBrainz is always silently dropped.

3. ✅ **Replace bare `except:` clauses** (`mp3_utils.py`): Multiple bare `except:` blocks mean permission errors, corrupt files, and IO failures all silently become "no metadata found."

4. ✅ **Add tests for `data_sources.py` core aggregation logic**: `search_all_sources()` and `enrich_with_all_sources()` have no dedicated tests. Partial failure (one source up, one down) is completely untested.

5. ✅ **Document the `enrich` command** (`README.md`): The README covers `search` and `info` but never mentions `enrich`, which is arguably the most important command.

6. **Add a size limit to artwork downloads** (`mp3_utils.py:212`): The full response is loaded into memory with no cap. A large or malicious image could exhaust memory.

7. **Make artwork support consistent across sources**: Bandcamp extracts and downloads artwork; MusicBrainz never does. Users get artwork or not depending on which source matched, with no indication why.

8. **Add filename parsing edge case tests**: `_parse_artist_title_from_filename()` has no tests for unusual inputs (multiple separators, bracket-only filenames, accented characters). Failures are silent — enrichment proceeds with wrong artist/title.
