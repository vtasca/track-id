"""Soulseek download integration via aioslsk."""

import asyncio
import difflib
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

# aioslsk is chatty about normal P2P connection failures; suppress below WARNING
logging.getLogger("aioslsk").setLevel(logging.WARNING)
from typing import Callable, List, Optional

from aioslsk.client import SoulSeekClient
from aioslsk.protocol.primitives import AttributeKey
from aioslsk.settings import CredentialsSettings, Settings, SharesSettings
from aioslsk.transfer.model import Transfer, TransferState

from .config import SoulseekConfig

_TERMINAL_STATES = {
    TransferState.State.COMPLETE,
    TransferState.State.FAILED,
    TransferState.State.ABORTED,
    TransferState.State.INCOMPLETE,
}

_MIN_FILE_BYTES = 500 * 1024       # 500 KB
_MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB
_SPEED_REFERENCE_BPS = 1_000_000   # 1 MB/s — avg_speed at/above this scores 1.0


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

        request = await self._client.searches.search(query)
        await asyncio.sleep(timeout)

        candidates: List[SlskResult] = []
        for sr in request.results:
            for fd in sr.shared_items:
                attrs = fd.get_attribute_map()
                bitrate = attrs.get(AttributeKey.BITRATE)
                duration = attrs.get(AttributeKey.DURATION)

                # Skip formats we can't use
                ext = fd.extension.lower().lstrip(".")
                if ext not in ("mp3", "flac", "ogg", "aac", "m4a", "wav"):
                    continue

                # Hard bitrate filter
                if bitrate is not None and bitrate < min_bitrate:
                    continue

                candidates.append(
                    SlskResult(
                        username=sr.username,
                        remote_path=fd.filename,
                        file_size=fd.filesize,
                        extension=fd.extension,
                        bitrate=bitrate,
                        duration=duration,
                        avg_speed=sr.avg_speed,
                        has_free_slots=sr.has_free_slots,
                    )
                )

        artist, _, title = query.partition(" - ")
        return rank_results(candidates, artist.strip(), title.strip() or query)

    async def download_file(
        self,
        candidate: SlskResult,
        dest: Path,
        on_progress: Optional[Callable[[int, Optional[int]], None]] = None,
        timeout: float = 180.0,
    ) -> Path:
        """Download one file from a candidate result and move it to dest."""
        assert self._client is not None, "Must be used as async context manager"

        transfer = await self._client.transfers.download(
            username=candidate.username,
            filename=candidate.remote_path,
        )

        success = await self._poll_transfer(transfer, timeout, on_progress)

        if not success:
            reason = transfer.fail_reason or transfer.abort_reason or "unknown"
            raise DownloadError(
                f"Download from {candidate.username} failed: {reason}"
            )

        if not transfer.local_path or not os.path.exists(transfer.local_path):
            raise DownloadError(
                f"Transfer completed but file not found at {transfer.local_path!r}"
            )

        if transfer.local_path != str(dest):
            shutil.move(transfer.local_path, dest)

        return dest

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
