"""Soulseek download integration via aioslsk."""

import asyncio
import difflib
import logging
import os
import re
import shutil
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from typing import Callable, List, Optional

from aioslsk.client import SoulSeekClient
from aioslsk.protocol.primitives import AttributeKey
from aioslsk.settings import CredentialsSettings, Settings, SharesSettings
from aioslsk.transfer.model import Transfer, TransferState

from .config import SoulseekConfig

logger = logging.getLogger(__name__)

_TERMINAL_STATES = {
    TransferState.State.COMPLETE,
    TransferState.State.FAILED,
    TransferState.State.ABORTED,
    TransferState.State.INCOMPLETE,
}

_MIN_FILE_BYTES = 500 * 1024       # 500 KB
_MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB
_SPEED_REFERENCE_BPS = 1_000_000   # 1 MB/s — avg_speed at/above this scores 1.0

_DEFAULT_PARALLELISM = 3           # candidates to race for an upload slot at once
_DEFAULT_QUEUE_TIMEOUT = 30.0      # seconds to wait in a peer's queue before moving on


class DownloadError(Exception):
    pass


@dataclass
class SlskResult:
    """A single candidate file from a Soulseek search."""
    username: str
    remote_path: str
    file_size: int
    extension: str
    bitrate: Optional[int]
    duration: Optional[int]
    avg_speed: int
    has_free_slots: bool
    score: float = field(default=0.0, compare=False)

    @property
    def display_name(self) -> str:
        return os.path.basename(self.remote_path.replace("\\", "/"))


def rank_results(
    results: List[SlskResult],
    artist: str,
    title: str,
) -> List[SlskResult]:
    """Score and sort candidates; highest score first.

    Scoring weights:
      40% — filename similarity to 'artist - title'
      20% — bitrate quality (320 kbps = 1.0, linear decay)
      12% — availability (peer has a free upload slot now)
      12% — format (.mp3 = 1.0, .flac = 0.6, other = 0.0)
       8% — peer average speed (1 MB/s = 1.0, linear decay)
       8% — file size sanity (500 KB – 50 MB = 1.0)

    Availability and speed matter because a Soulseek download isn't pulled from
    a swarm — it comes from one peer who must grant an upload slot. A peer with
    no free slots queues you (often for a long time), so a ready, fast peer is
    worth far more than a marginally better-named file from a busy one.
    """
    target = f"{artist} - {title}".lower()
    scored = []

    for r in results:
        # Filename similarity
        name = re.sub(r"[_\.\[\]\(\)]", " ", r.display_name.lower())
        name = os.path.splitext(name)[0]
        filename_score = difflib.SequenceMatcher(None, target, name).ratio()

        # Bitrate quality (0–320 kbps normalised to 0–1)
        if r.bitrate and r.bitrate > 0:
            bitrate_score = min(r.bitrate / 320.0, 1.0)
        else:
            bitrate_score = 0.3  # unknown bitrate — mild penalty

        # Format preference
        ext = r.extension.lower().lstrip(".")
        if ext == "mp3":
            format_score = 1.0
        elif ext == "flac":
            format_score = 0.6
        else:
            format_score = 0.0

        # File size sanity
        if _MIN_FILE_BYTES <= r.file_size <= _MAX_FILE_BYTES:
            size_score = 1.0
        else:
            size_score = 0.0

        # Availability — a free upload slot means we can start now instead of
        # waiting in the peer's queue.
        availability_score = 1.0 if r.has_free_slots else 0.0

        # Peer average speed (bytes/sec), normalised to 0–1 against a 1 MB/s
        # reference. avg_speed is the server-reported upload speed for the peer.
        if r.avg_speed and r.avg_speed > 0:
            speed_score = min(r.avg_speed / _SPEED_REFERENCE_BPS, 1.0)
        else:
            speed_score = 0.0

        r.score = (
            0.40 * filename_score
            + 0.20 * bitrate_score
            + 0.12 * availability_score
            + 0.12 * format_score
            + 0.08 * speed_score
            + 0.08 * size_score
        )
        scored.append(r)

    scored.sort(key=lambda x: x.score, reverse=True)
    return scored


def _sanitize_filename(s: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s).strip()


# Map a claimed extension to the set of container formats whose magic bytes
# we accept for it. Several extensions share a container (m4a/aac/mp4) or are
# routinely mislabeled between lossy/lossless siblings.
_FORMAT_ALIASES = {
    "mp3": {"mp3"},
    "flac": {"flac"},
    "ogg": {"ogg"},
    "wav": {"wav"},
    "m4a": {"mp4"},
    "aac": {"mp4", "aac"},
}


def _sniff_audio_format(path: Path) -> Optional[str]:
    """Identify a file's real container from its header bytes.

    Returns a canonical format name (``mp3``, ``flac``, ``ogg``, ``wav``,
    ``mp4``, ``aac``) or ``None`` if the bytes match no known audio format —
    e.g. an HTML error page or truncated junk served under a music filename.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(16)
    except OSError:
        return None

    if len(head) < 4:
        return None

    if head[:4] == b"fLaC":
        return "flac"
    if head[:4] == b"OggS":
        return "ogg"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[4:8] == b"ftyp":
        return "mp4"
    if head[:3] == b"ID3":
        return "mp3"
    # MPEG audio frame sync: 11 set bits (0xFFE).
    if head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        # ADTS AAC streams share the sync word; layer bits 0b00 mark AAC.
        if (head[1] & 0x06) == 0x00:
            return "aac"
        return "mp3"
    return None


class SoulseekDownloader:
    """Async context manager wrapping an aioslsk client."""

    def __init__(self, config: SoulseekConfig, download_dir: Path) -> None:
        self._config = config
        self._download_dir = download_dir
        self._client: Optional[SoulSeekClient] = None

    def _build_settings(self) -> Settings:
        return Settings(
            credentials=CredentialsSettings(
                username=self._config.username,
                password=self._config.password,
            ),
            shares=SharesSettings(download=str(self._download_dir)),
        )

    async def __aenter__(self) -> "SoulseekDownloader":
        self._client = SoulSeekClient(self._build_settings())
        await self._client.start()
        await self._client.login()
        # Give the distributed network a moment to establish peer connections
        # before issuing a search — searching immediately after login returns
        # far fewer results than a fully-connected client.
        await asyncio.sleep(10)
        return self

    async def __aexit__(self, *_) -> None:
        if self._client is not None:
            await self._client.stop()
            self._client = None

    async def search(
        self,
        query: str,
        timeout: float,
        min_bitrate: int,
    ) -> List[SlskResult]:
        """Search the network and return ranked, filtered results."""
        assert self._client is not None, "Must be used as async context manager"

        logger.info("Searching Soulseek for %r (timeout=%.0fs, min_bitrate=%d)", query, timeout, min_bitrate)
        request = await self._client.searches.search(query)
        await asyncio.sleep(timeout)

        candidates: List[SlskResult] = []
        raw_file_count = 0
        rejected_format: Counter[str] = Counter()
        rejected_bitrate = 0
        rejected_files: List[str] = []
        for sr in request.results:
            for fd in sr.shared_items:
                raw_file_count += 1
                attrs = fd.get_attribute_map()
                bitrate = attrs.get(AttributeKey.BITRATE)
                duration = attrs.get(AttributeKey.DURATION)
                name = os.path.basename(fd.filename.replace("\\", "/"))

                # Skip formats we can't use. Many peers leave the protocol
                # `extension` field blank, so fall back to the filename suffix.
                ext = fd.extension.lower().lstrip(".")
                if not ext:
                    ext = os.path.splitext(name)[1].lower().lstrip(".")
                if ext not in ("mp3", "flac", "ogg", "aac", "m4a", "wav"):
                    rejected_format[ext or "<none>"] += 1
                    rejected_files.append(f"{name} [format:{ext or '<none>'}]")
                    continue

                # Hard bitrate filter
                if bitrate is not None and bitrate < min_bitrate:
                    rejected_bitrate += 1
                    rejected_files.append(f"{name} [{bitrate}kbps]")
                    continue

                candidates.append(
                    SlskResult(
                        username=sr.username,
                        remote_path=fd.filename,
                        file_size=fd.filesize,
                        extension=ext,
                        bitrate=bitrate,
                        duration=duration,
                        avg_speed=sr.avg_speed,
                        has_free_slots=sr.has_free_slots,
                    )
                )

        artist, _, title = query.partition(" - ")
        ranked = rank_results(candidates, artist.strip(), title.strip() or query)
        logger.info(
            "Search %r returned %d usable candidate(s) (%d raw file(s) from %d peer(s) before filtering)",
            query,
            len(ranked),
            raw_file_count,
            len(request.results),
        )
        if not ranked and raw_file_count:
            format_summary = ", ".join(
                f"{ext}×{n}" for ext, n in rejected_format.most_common()
            ) or "none"
            logger.info(
                "All %d raw file(s) for %r were filtered out — "
                "rejected by bitrate<%d: %d, rejected by format: %d (%s)",
                raw_file_count,
                query,
                min_bitrate,
                rejected_bitrate,
                sum(rejected_format.values()),
                format_summary,
            )
            for entry in rejected_files:
                logger.info("  rejected: %s", entry)
        return ranked

    async def download_file(
        self,
        candidate: SlskResult,
        dest: Path,
        on_progress: Optional[Callable[[int, Optional[int]], None]] = None,
        timeout: float = 180.0,
    ) -> Path:
        """Download one file from a candidate result and move it to dest."""
        assert self._client is not None, "Must be used as async context manager"

        logger.info("Requesting %s from %s", candidate.display_name, candidate.username)
        transfer = await self._client.transfers.download(
            username=candidate.username,
            filename=candidate.remote_path,
        )

        success = await self._poll_transfer(transfer, timeout, on_progress)

        if not success:
            reason = transfer.fail_reason or transfer.abort_reason or "unknown"
            logger.warning("Download from %s failed: %s", candidate.username, reason)
            raise DownloadError(
                f"Download from {candidate.username} failed: {reason}"
            )

        logger.info("Download from %s succeeded -> %s", candidate.username, dest)
        return self._finalize_transfer(transfer, dest, candidate.extension)

    async def race_download(
        self,
        candidates: List[SlskResult],
        dest: Path,
        on_attempt: Optional[Callable[[SlskResult], None]] = None,
        on_start: Optional[Callable[[SlskResult], None]] = None,
        on_progress: Optional[Callable[[int, Optional[int]], None]] = None,
        parallelism: int = _DEFAULT_PARALLELISM,
        queue_timeout: float = _DEFAULT_QUEUE_TIMEOUT,
        download_timeout: float = 180.0,
    ) -> Path:
        """Race several candidates for an upload slot; first to start sending wins.

        A Soulseek transfer is slot-gated: requesting a file only places you in
        the peer's upload queue. Instead of waiting out one peer's queue before
        trying the next, we request up to `parallelism` candidates at once and
        take the first peer that actually starts sending bytes, aborting the
        rest. A candidate that fails outright, or sits queued past
        `queue_timeout` without starting, is dropped and replaced by the next
        candidate in line. If the winning transfer then fails mid-download, we
        fall back to whatever candidates remain.

        `on_attempt` fires when a candidate is requested, `on_start` when one
        wins the race and begins downloading, `on_progress` during that download.
        """
        assert self._client is not None, "Must be used as async context manager"

        pending = list(candidates)
        # Each entry: [transfer, candidate, requested_at]
        active: List[List] = []

        async def _fill() -> None:
            while pending and len(active) < parallelism:
                cand = pending.pop(0)
                if on_attempt:
                    on_attempt(cand)
                transfer = await self._client.transfers.download(
                    username=cand.username,
                    filename=cand.remote_path,
                )
                active.append([transfer, cand, time.monotonic()])

        await _fill()

        winner: Optional[List] = None
        while active and winner is None:
            now = time.monotonic()
            for entry in list(active):
                transfer, cand, requested_at = entry
                state = transfer.state.VALUE
                started = transfer.start_time is not None or transfer.bytes_transfered > 0

                if started and state in (
                    TransferState.State.DOWNLOADING,
                    TransferState.State.COMPLETE,
                ):
                    winner = entry
                    break
                if state in _TERMINAL_STATES:
                    # Failed/aborted before it ever started — drop and refill.
                    active.remove(entry)
                    await _fill()
                elif now - requested_at > queue_timeout:
                    # Stuck in the peer's queue too long — abort and refill.
                    await self._safe_abort(transfer)
                    active.remove(entry)
                    await _fill()

            if winner is None and active:
                await asyncio.sleep(0.25)

        if winner is None:
            raise DownloadError(
                f"No peer granted an upload slot for '{dest.stem}' "
                f"(tried {len(candidates)} candidate(s))"
            )

        win_transfer, win_cand, _ = winner
        # Abort the losers so we don't waste their bandwidth or ours.
        for transfer, _cand, _ts in active:
            if transfer is not win_transfer:
                await self._safe_abort(transfer)

        if on_start:
            on_start(win_cand)

        success = await self._poll_transfer(win_transfer, download_timeout, on_progress)
        if not success:
            # The winner stalled or failed after starting; try the rest.
            if pending:
                return await self.race_download(
                    pending, dest,
                    on_attempt=on_attempt,
                    on_start=on_start,
                    on_progress=on_progress,
                    parallelism=parallelism,
                    queue_timeout=queue_timeout,
                    download_timeout=download_timeout,
                )
            reason = win_transfer.fail_reason or win_transfer.abort_reason or "unknown"
            raise DownloadError(
                f"Download from {win_cand.username} failed: {reason}"
            )

        return self._finalize_transfer(win_transfer, dest, win_cand.extension)

    async def _safe_abort(self, transfer: Transfer) -> None:
        """Abort a transfer, swallowing errors from already-terminal transfers."""
        try:
            await self._client.transfers.abort(transfer)  # type: ignore[union-attr]
        except Exception:
            pass

    def _finalize_transfer(
        self,
        transfer: Transfer,
        dest: Path,
        expected_ext: Optional[str] = None,
    ) -> Path:
        """Validate a completed transfer's file and move it to dest."""
        if not transfer.local_path or not os.path.exists(transfer.local_path):
            raise DownloadError(
                f"Transfer completed but file not found at {transfer.local_path!r}"
            )

        self._verify_format(Path(transfer.local_path), expected_ext)

        if transfer.local_path != str(dest):
            shutil.move(transfer.local_path, dest)

        return dest

    def _verify_format(self, path: Path, expected_ext: Optional[str]) -> None:
        """Confirm the downloaded bytes are real audio of the claimed format.

        The filename is whatever a stranger on the network typed, so we sniff
        the header rather than trust the extension. A file that is not audio at
        all is rejected (the caller can fall back to another peer); a genuine
        audio file whose container merely disagrees with its extension is kept
        but logged, since the content is still usable.
        """
        actual = _sniff_audio_format(path)
        if actual is None:
            raise DownloadError(
                f"Downloaded file {path.name!r} is not a recognized audio "
                f"format (header did not match mp3/flac/ogg/wav/mp4/aac)"
            )

        ext = (expected_ext or "").lower().lstrip(".")
        if ext and actual not in _FORMAT_ALIASES.get(ext, {ext}):
            logger.warning(
                "Format mismatch for %s: filename claims .%s but content is %s",
                path.name,
                ext,
                actual,
            )

    async def _poll_transfer(
        self,
        transfer: Transfer,
        timeout: float,
        on_progress: Optional[Callable[[int, Optional[int]], None]],
    ) -> bool:
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            state = transfer.state.VALUE
            if on_progress:
                on_progress(transfer.bytes_transfered, transfer.filesize)
            if state in _TERMINAL_STATES:
                break
            await asyncio.sleep(0.25)

        return transfer.state.VALUE == TransferState.State.COMPLETE
