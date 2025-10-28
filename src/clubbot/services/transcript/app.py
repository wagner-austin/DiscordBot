from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ...config import Config
from ...utils.youtube import extract_video_id, validate_youtube_url
from .cleaner import clean_segments
from .provider import TranscriptProvider, YouTubeTranscriptProvider
from .stt_provider import STTTranscriptProvider
from .types import DEFAULT_TRANSCRIPT_LANGS, TranscriptOptions, TranscriptResult


def _parse_langs(spec: str | None) -> list[str]:
    raw = (spec or "").strip()
    if not raw:
        return DEFAULT_TRANSCRIPT_LANGS
    return [p.strip() for p in raw.split(",") if p.strip()]


@dataclass(frozen=True)
class TranscriptService:
    cfg: Config
    provider: TranscriptProvider = field(init=False, repr=False)
    _logger: logging.Logger = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_logger", logging.getLogger(__name__))
        provider_name = (self.cfg.TRANSCRIPT_PROVIDER or "youtube").strip().lower()
        if provider_name == "stt":
            api_key = self.cfg.OPENAI_API_KEY
            if not api_key:
                raise RuntimeError(
                    "TRANSCRIPT_PROVIDER=stt requires OPENAI_API_KEY (or OPEN_AI_API_KEY)"
                )
            stt = STTTranscriptProvider(
                api_key=api_key,
                max_video_seconds=self.cfg.TRANSCRIPT_MAX_VIDEO_SECONDS,
                max_file_mb=self.cfg.TRANSCRIPT_MAX_FILE_MB,
                timeout_seconds=float(getattr(self.cfg, "TRANSCRIPT_STT_API_TIMEOUT_SECONDS", 900)),
                max_retries=int(getattr(self.cfg, "TRANSCRIPT_STT_API_MAX_RETRIES", 2)),
                cookies_text=getattr(self.cfg, "TRANSCRIPT_COOKIES_TEXT", None),
                cookies_path=getattr(self.cfg, "TRANSCRIPT_COOKIES_PATH", None),
                enable_chunking=bool(getattr(self.cfg, "TRANSCRIPT_ENABLE_CHUNKING", True)),
                chunk_threshold_mb=float(getattr(self.cfg, "TRANSCRIPT_CHUNK_THRESHOLD_MB", 20.0)),
                target_chunk_mb=float(getattr(self.cfg, "TRANSCRIPT_TARGET_CHUNK_MB", 20.0)),
                max_chunk_duration=float(
                    getattr(self.cfg, "TRANSCRIPT_MAX_CHUNK_DURATION_SECONDS", 600.0)
                ),
                max_concurrent_chunks=int(getattr(self.cfg, "TRANSCRIPT_MAX_CONCURRENT_CHUNKS", 3)),
                silence_threshold_db=float(
                    getattr(self.cfg, "TRANSCRIPT_SILENCE_THRESHOLD_DB", -40.0)
                ),
                silence_duration=float(
                    getattr(self.cfg, "TRANSCRIPT_SILENCE_DURATION_SECONDS", 0.5)
                ),
                stt_rtf=float(getattr(self.cfg, "TRANSCRIPT_STT_RTF", 0.5)),
                dl_mib_per_sec=float(getattr(self.cfg, "TRANSCRIPT_DL_MIB_PER_SEC", 4.0)),
            )
            object.__setattr__(self, "provider", stt)
        else:
            object.__setattr__(self, "provider", YouTubeTranscriptProvider())

    def fetch_cleaned(self, url: str) -> TranscriptResult:
        canonical = validate_youtube_url(url)
        vid = extract_video_id(canonical)
        langs = _parse_langs(getattr(self.cfg, "TRANSCRIPT_PREFERRED_LANGS", None))
        opts = TranscriptOptions(preferred_langs=langs)
        self._logger.debug("Fetching transcript: vid=%s langs=%s", vid, langs)
        segments = self.provider.fetch(vid, opts)
        text = clean_segments(segments)
        return TranscriptResult(url=canonical, video_id=vid, text=text)

    # For tests only: allow provider injection without breaking frozen dataclass
    # (exercised in tests)
    def _set_provider_for_tests(self, provider: TranscriptProvider) -> None:  # pragma: no cover
        object.__setattr__(self, "provider", provider)
