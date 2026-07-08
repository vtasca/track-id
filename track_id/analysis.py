"""Per-file audio inspection shared by the analyze and doctor commands.

Also home to the filename/format utilities (sanitizing, magic-byte sniffing)
that the Soulseek downloader re-exports, so inspecting a file never has to
import aioslsk.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from mutagen.id3 import ID3, ID3NoHeaderError, ID3TagError
from mutagen.mp3 import MP3, BitrateMode, HeaderNotFoundError

# Tags a well-tagged track is expected to carry (subset of id3_tags.py).
CORE_TAGS = ("TIT2", "TPE1", "TALB", "TDRC")


def sanitize_filename(s: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s).strip()


# Map a claimed extension to the set of container formats whose magic bytes
# we accept for it. Several extensions share a container (m4a/aac/mp4) or are
# routinely mislabeled between lossy/lossless siblings.
FORMAT_ALIASES = {
    "mp3": {"mp3"},
    "flac": {"flac"},
    "ogg": {"ogg"},
    "wav": {"wav"},
    "m4a": {"mp4"},
    "aac": {"mp4", "aac"},
}


def sniff_audio_format(path: Path) -> Optional[str]:
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


@dataclass
class FileReport:
    """Everything inspect_file() could learn about one audio file."""

    path: Path
    file_size: int
    claimed_format: str                 # from the file extension
    actual_format: Optional[str]        # sniffed from magic bytes; None = unrecognized
    readable: bool = False              # mutagen could parse the audio stream
    duration_seconds: float = 0.0
    bitrate: Optional[int] = None       # bits per second
    bitrate_mode: str = "unknown"       # CBR / VBR / ABR / unknown
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    encoder: str = ""
    tags: Dict[str, str] = field(default_factory=dict)
    has_artwork: bool = False

    @property
    def format_mismatch(self) -> bool:
        """True when the bytes don't plausibly match the extension."""
        accepted = FORMAT_ALIASES.get(self.claimed_format, {self.claimed_format})
        return self.actual_format not in accepted

    @property
    def missing_tags(self) -> List[str]:
        return [t for t in CORE_TAGS if not self.tags.get(t)]

    def problems(self, min_bitrate_kbps: int = 0) -> List[str]:
        """Human-readable list of everything wrong with this file."""
        found = []
        if self.actual_format is None:
            found.append("not a recognized audio file")
        elif self.format_mismatch:
            found.append(f"bytes are {self.actual_format}, extension says {self.claimed_format}")
        elif not self.readable:
            found.append("audio stream could not be parsed")
        if self.readable and min_bitrate_kbps and self.bitrate:
            if self.bitrate < min_bitrate_kbps * 1000:
                found.append(f"bitrate {self.bitrate // 1000} kbps < {min_bitrate_kbps} kbps")
        if self.missing_tags:
            found.append(f"missing tags: {', '.join(self.missing_tags)}")
        if not self.has_artwork:
            found.append("no artwork")
        return found


_BITRATE_MODE_NAMES = {
    BitrateMode.CBR: "CBR",
    BitrateMode.VBR: "VBR",
    BitrateMode.ABR: "ABR",
}


def inspect_file(path: str) -> FileReport:
    """Inspect one audio file: container format, stream properties, tags.

    Never raises on malformed input — a file full of junk bytes simply comes
    back with ``actual_format=None`` and ``readable=False``.
    """
    p = Path(path)
    report = FileReport(
        path=p,
        file_size=p.stat().st_size if p.exists() else 0,
        claimed_format=p.suffix.lower().lstrip("."),
        actual_format=sniff_audio_format(p),
    )

    try:
        audio = MP3(str(p))
        info: Any = audio.info
        report.readable = True
        report.duration_seconds = info.length
        report.bitrate = getattr(info, "bitrate", None)
        mode = getattr(info, "bitrate_mode", None)
        if mode is not None:
            report.bitrate_mode = _BITRATE_MODE_NAMES.get(mode, "unknown")
        report.sample_rate = getattr(info, "sample_rate", None)
        report.channels = getattr(info, "channels", None)
        report.encoder = " ".join(
            part for part in (
                getattr(info, "encoder_info", ""), getattr(info, "encoder_settings", "")
            ) if part
        )
    except (HeaderNotFoundError, OSError):
        pass

    try:
        id3 = ID3(str(p))
        for key, value in id3.items():
            if hasattr(value, "text"):
                report.tags[key] = str(value.text[0]) if value.text else ""
        report.has_artwork = any(key.startswith("APIC") for key in id3.keys())
    except (ID3NoHeaderError, ID3TagError, OSError):
        pass

    return report


def iter_audio_files(directory: Path, extension: str = "mp3") -> List[Path]:
    """All files under ``directory`` (recursive) with the given extension, sorted."""
    return sorted(
        p for p in directory.rglob(f"*.{extension}")
        if p.is_file() and not os.path.basename(p).startswith(".")
    )
