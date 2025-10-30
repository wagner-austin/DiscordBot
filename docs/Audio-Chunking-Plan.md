# Audio Chunking Implementation Plan

## Overview

Implement audio chunking to bypass Whisper API's 25 MB limit, enabling transcription of larger videos through parallel processing with silence-based splitting.


## Codebase Alignment Summary

- Provider contract is synchronous; plan uses thread-based concurrency to fit it.
- Use UserInputError for user-facing failures; log detailed context.
- Use logging.getLogger(__name__) so instance/request IDs flow via existing logging.
- Strict typing throughout; add shared chunk type in types.py.
- Keep responsibilities isolated (chunking/parsing in chunker.py; no cross-module duplication).
## Problem Statement

**Current limitations:**
- Whisper API has a 25 MB audio file size limit
- Videos longer than ~15-20 minutes often exceed this limit
- Users get blocked with "Audio file exceeds 25 MB" error

**Proposed solution:**
- Split large audio files into smaller chunks at silence points
- Process chunks in parallel with Whisper API
- Merge transcripts with proper timestamp alignment
- Enable processing of 90-minute videos (current TRANSCRIPT_MAX_VIDEO_SECONDS)

## Design Goals

1. **Reliability**: Robust error handling, graceful fallbacks
2. **Quality**: Clean splits at silence points to avoid cutting mid-word
3. **Performance**: Parallel processing to maintain/improve speed
4. **Observability**: Clear logging of chunking progress
5. **Configuration**: Allow users to tune chunking behavior

## Architecture

### Components

- STTTranscriptProvider (existing): decides when chunking is needed; orchestrates chunker, transcriber, and merger.
- AudioChunker (new): detects silence, calculates split points, splits via ffmpeg stream copy.
- ParallelTranscriber (new): bounded thread-based concurrency for Whisper calls, retries/timeouts.
- TranscriptMerger (new): adjusts timestamps by chunk offsets and concatenates segments in order.

### File Structure

```
src/clubbot/services/transcript/
  app.py                 # TranscriptService (existing)
  stt_provider.py        # STTTranscriptProvider (modify)
  types.py               # Shared types (add AudioChunk)
  `chunker.py`             # AudioChunker (NEW)
  parallel.py            # ParallelTranscriber (NEW)
  merger.py              # TranscriptMerger (NEW)

tests/clubbot/services/
  test_audio_chunker.py              # Test chunking logic (NEW)
  test_parallel_transcriber.py       # Test parallel API calls (NEW)
  test_transcript_merger.py          # Test merging logic (NEW)
```

## Implementation Details

### 0. Types (update `types.py`)

Introduce a shared chunk type for clarity and mypy friendliness:

```python
from dataclasses import dataclass
from .types import TranscriptSegment

@dataclass(frozen=True)
class AudioChunk:
    path: str
    start_seconds: float
    duration_seconds: float
    size_bytes: int

# For readability in signatures
TranscriptSegmentList = list[TranscriptSegment]
```

### 1. AudioChunker (`chunker.py`)

**Purpose:** Split audio files at optimal silence points

**Key methods:**
```python
class AudioChunker:
    def chunk_audio(
        self,
        audio_path: str,
        total_duration: float,
        estimated_mb: float
    ) -> list[AudioChunk]:
        """Main entry point. Returns list of chunks or single file if no chunking needed."""

    def _detect_silence(self, audio_path: str, duration: float) -> list[float]:
        """Use ffmpeg silencedetect filter to find silence timestamps."""

    def _calculate_split_points(
        self,
        silence_points: list[float],
        total_duration: float,
        estimated_mb: float
    ) -> list[float]:
        """Determine optimal split points based on silence and target chunk size."""

    def _split_audio(
        self,
        audio_path: str,
        split_points: list[float],
        total_duration: float
    ) -> list[AudioChunk]:
        """Split audio at specified points using ffmpeg -ss and -t."""
```

**Silence detection approach:**
```bash
# ffmpeg command for silence detection
ffmpeg -i input.webm \
  -af "silencedetect=n=-40dB:d=0.5" \
  -f null -

# Output parsing:
# [silencedetect @ ...] silence_start: 123.456
# [silencedetect @ ...] silence_end: 125.789 | silence_duration: 2.333
```

**Splitting strategy:**
1. Calculate target number of chunks: `ceil(file_size_mb / target_chunk_mb)`
2. Calculate ideal split times: `[duration / num_chunks * i for i in range(1, num_chunks)]`
3. For each ideal time, find nearest silence point within +/- 30% tolerance
4. If no silence nearby, use ideal time as fallback
5. Split using ffmpeg stream copy (no re-encoding for speed)

**Edge cases:**
- No silence detected -> fall back to time-based splitting
- ffmpeg not available -> raise error with clear message
- Silence detection timeout -> fall back to time-based splitting
- Very short audio (< target_chunk_mb) -> return single chunk, skip splitting

### 2. ParallelTranscriber (`parallel.py`)

Purpose: process multiple chunks concurrently using a thread pool to match the synchronous Whisper API call path, with retries and timeouts.

Key shape (matches code):
```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import BinaryIO, Literal, Protocol

class TranscribeFn(Protocol):
    def __call__(
        *,
        model: str,
        file: BinaryIO,
        response_format: Literal["verbose_json"],
        timeout: float | None = None,
    ) -> object: ...

class ParallelTranscriber:
    def __init__(
        self,
        *,
        transcribe: TranscribeFn,
        max_concurrent: int = 3,
        max_retries: int = 2,
        timeout_seconds: float = 900.0,
        logger: logging.Logger | None = None,
    ) -> None:
        self._transcribe = transcribe
        ...

    def transcribe_chunks(self, chunks: list[AudioChunk]) -> list[TranscriptSegmentList]:
        def work(chunk: AudioChunk) -> TranscriptSegmentList:
            attempt = 0
            while True:
                attempt += 1
                try:
                    with open(chunk.path, "rb") as f:
                        resp = self._transcribe(
                            model="whisper-1", file=f, response_format="verbose_json", timeout=self._timeout
                        )
                    return _convert_verbose_to_segments(resp)
                except Exception as e:
                    if attempt <= self._max_retries:
                        ...
                        continue
                    raise
        ...
```
Rate limiting considerations:
- OpenAI Whisper: keep concurrency modest (default 3). Configurable.
- API timeout: use `TRANSCRIPT_STT_API_TIMEOUT_SECONDS` per chunk.
- Retry logic: use provider-level `max_retries`.
- Progress tracking: log start/completion per chunk.

Error handling:
- If any chunk fails after retries -> raise UserInputError in the provider.
- Preserve original exception details in logs.
- Clean up temp files on error in the provider (see Cleanup Strategy).
### 3. TranscriptMerger (`merger.py`)

**Purpose:** Combine transcripts from chunks with timestamp adjustment

**Key methods:**
```python
class TranscriptMerger:
    def merge(
        self,
        chunk_results: list[tuple[AudioChunk, list[TranscriptSegment]]],
    ) -> list[TranscriptSegment]:
        """Merge segments from all chunks into single transcript."""

    def _adjust_timestamps(
        self,
        segments: list[TranscriptSegment],
        offset_seconds: float,
    ) -> list[TranscriptSegment]:
        """Add offset to segment start times."""

    def _deduplicate_overlaps(
        self,
        segments: list[TranscriptSegment],
    ) -> list[TranscriptSegment]:
        """Remove duplicate text at chunk boundaries (future enhancement)."""
```

**Merging strategy:**
1. For each chunk, adjust timestamps by adding chunk's start_seconds offset
2. Concatenate all segments in chunk order
3. Sort by start time (should already be sorted, but defensive)
4. Optional: Deduplicate text at boundaries (v2 feature)

**Timestamp adjustment:**
```python
# Example:
# Chunk 0: start=0s, segments=[{"text": "Hello", "start": 0.0, "duration": 1.0}]
# Chunk 1: start=300s, segments=[{"text": "World", "start": 0.0, "duration": 1.0}]
#
# After merge:
# [{"text": "Hello", "start": 0.0, "duration": 1.0},
#  {"text": "World", "start": 300.0, "duration": 1.0}]
```

### 4. STTTranscriptProvider Updates (`stt_provider.py`)

**Changes needed:**

```python
def _transcribe(self, audio_path: str) -> list[TranscriptSegment]:
    # NEW: Check if chunking enabled and needed
    if self._should_chunk(audio_path):
        return self._transcribe_chunked(audio_path)
    else:
        # Existing single-file transcription
        return self._transcribe_single_file(audio_path)

def _should_chunk(self, audio_path: str) -> bool:
    """Determine if file needs chunking based on size."""
    if not self.enable_chunking:
        return False

    size_bytes = os.path.getsize(audio_path)
    size_mb = size_bytes / (1024 * 1024)
    return size_mb > self.chunk_threshold_mb

def _transcribe_chunked(self, audio_path: str) -> list[TranscriptSegment]:
    """Transcribe large file using chunking (sync provider, thread pool concurrency)."""
    # 1. Get duration estimate
    duration = self._get_audio_duration(audio_path)
    size_mb = os.path.getsize(audio_path) / (1024 * 1024)

    # 2. Chunk audio
    chunker = AudioChunker(
        target_chunk_mb=self.target_chunk_mb,
        max_chunk_duration_seconds=self.max_chunk_duration,
        silence_threshold_db=self.silence_threshold_db,
        silence_duration_seconds=self.silence_duration,
        logger=self._logger,
    )
    chunks = chunker.chunk_audio(audio_path, duration, size_mb)

    # 3. Transcribe chunks in parallel (threads)
    transcriber = ParallelTranscriber(
        client=self._client,
        max_concurrent=self.max_concurrent_chunks,
        max_retries=self.max_retries,
        timeout_seconds=self.timeout_seconds,
        logger=self._logger,
    )
    chunk_results = transcriber.transcribe_chunks(chunks)

    # 4. Merge results
    merger = TranscriptMerger()
    merged = merger.merge(list(zip(chunks, chunk_results)))

    # 5. Clean up chunk files
    for chunk in chunks:
        if chunk.path != audio_path:  # Don't delete original
            with contextlib.suppress(Exception):
                os.remove(chunk.path)

    return merged
def _get_audio_duration(self, audio_path: str) -> float:
    """Get audio duration using ffprobe."""
    # Use ffprobe to get exact duration
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])
```

**New dataclass fields:**
```python
@dataclass
class STTTranscriptProvider:
    # Existing fields...

    # New chunking configuration
    enable_chunking: bool = True
    chunk_threshold_mb: float = 20.0  # Start chunking above this size
    target_chunk_mb: float = 20.0  # Target size per chunk
    max_chunk_duration: float = 600.0  # 10 minutes max per chunk
    max_concurrent_chunks: int = 3  # Max parallel API calls
    silence_threshold_db: float = -40.0  # dB level for silence detection
    silence_duration: float = 0.5  # Minimum silence duration (seconds)
```

## Configuration

**New environment variables:**

```bash
# Enable/disable chunking (default: true)
TRANSCRIPT_ENABLE_CHUNKING=true

# Start chunking when audio file exceeds this size (default: 20 MB)
TRANSCRIPT_CHUNK_THRESHOLD_MB=20

# Target size per chunk (default: 20 MB, safely under 25 MB limit)
TRANSCRIPT_TARGET_CHUNK_MB=20

# Maximum chunk duration as fallback (default: 600 seconds = 10 min)
TRANSCRIPT_MAX_CHUNK_DURATION_SECONDS=600

# Maximum concurrent Whisper API calls (default: 3, respects rate limits)
TRANSCRIPT_MAX_CONCURRENT_CHUNKS=3

# Silence detection threshold in dB (default: -40)
TRANSCRIPT_SILENCE_THRESHOLD_DB=-40.0

# Minimum silence duration to split at in seconds (default: 0.5)
TRANSCRIPT_SILENCE_DURATION_SECONDS=0.5
```

**Config class updates (`src/clubbot/config.py`):**

Add these fields to Config and wire them in load_config() consistent with existing patterns:



```python
@dataclass(frozen=True)
class Config:
    # ... existing fields ...

    # Chunking configuration
    TRANSCRIPT_ENABLE_CHUNKING: bool = True
    TRANSCRIPT_CHUNK_THRESHOLD_MB: float = 20.0
    TRANSCRIPT_TARGET_CHUNK_MB: float = 20.0
    TRANSCRIPT_MAX_CHUNK_DURATION_SECONDS: float = 600.0
    TRANSCRIPT_MAX_CONCURRENT_CHUNKS: int = 3
    TRANSCRIPT_SILENCE_THRESHOLD_DB: float = -40.0
    TRANSCRIPT_SILENCE_DURATION_SECONDS: float = 0.5
```

## Dependencies

**Required:**
- `ffmpeg` - Must be installed on system (for splitting/silence detection)
- `ffprobe` - Usually comes with ffmpeg (for duration extraction)

**Python packages (already available):**
- `concurrent.futures` - For thread-based parallel processing
- `subprocess` - For ffmpeg calls
- `json` - For ffprobe output parsing

**Installation check:**
Add to bot startup to verify ffmpeg availability:
```python
def check_dependencies():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True, timeout=5)
        logging.info("ffmpeg is available")
    except (FileNotFoundError, subprocess.CalledProcessError):
        logging.warning("ffmpeg not found; audio chunking will not be available")
```

**Docker/Deployment:**
- Current Dockerfile does not install ffmpeg.
- Add ffmpeg to Dockerfile:
  ```dockerfile
  RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*
  ```

## Error Handling

### Failure Scenarios

1. **ffmpeg not available:**
   - Detection: Run `ffmpeg -version` on provider init
   - Response: Disable chunking, log warning, fall back to 25 MB limit
   - User message: "Audio file exceeds 25 MB (ffmpeg not available for chunking)"

2. **Silence detection fails/times out:**
   - Response: Fall back to time-based splitting
   - Log: Warning with reason
   - Continue with fallback

3. **Chunk splitting fails:**
   - Clean up any partial chunks
   - Raise UserInputError with clear message
   - User message: "Failed to process audio file. Please try again."

4. **Single chunk transcription fails:**
   - Retry per existing retry logic
   - If all retries fail, raise error
   - Clean up all chunks
   - User message: "Transcription failed due to API error. Please try again."

5. **Partial success (some chunks fail):**
   - Fail fast - if any chunk fails after retries, whole job fails
   - Clean up all chunks
   - Log which chunk failed for debugging

### Cleanup Strategy

```python
# Use try/finally pattern
chunks = []
try:
    chunks = chunker.chunk_audio(...)
    results = await transcriber.transcribe_chunks(chunks)
    return merger.merge(zip(chunks, results))
finally:
    # Always clean up temp chunks
    for chunk in chunks:
        if chunk.path != original_audio_path:
            with contextlib.suppress(Exception):
                os.remove(chunk.path)
    # Clean up chunk directory
    if chunks and os.path.dirname(chunks[0].path) != os.path.dirname(original_audio_path):
        with contextlib.suppress(Exception):
            os.rmdir(os.path.dirname(chunks[0].path))
```

## Testing Strategy

### Unit Tests

1. **test_audio_chunker.py:**
   - Test silence detection parsing
   - Test split point calculation
   - Test time-based fallback
   - Test single-file passthrough (no chunking needed)
   - Mock ffmpeg calls for speed

2. **test_parallel_transcriber.py:**
   - Test concurrent API calls with mocked OpenAI client
   - Test rate limiting (max_concurrent respected)
   - Test error handling (single chunk failure)
   - Test retry logic

3. **test_transcript_merger.py:**
   - Test timestamp adjustment
   - Test segment ordering
   - Test empty chunks handling
   - Test single chunk passthrough

### Integration Tests

4. **test_stt_chunking_integration.py:**
   - Test end-to-end with small test audio file
   - Test with ffmpeg not available (graceful degradation)
   - Test with mock OpenAI responses
   - Verify cleanup of temp files

### Manual Testing

5. **Railway deployment test:**
   - Deploy with ffmpeg installed
   - Test with real 30-minute video (should chunk)
   - Test with real 5-minute video (should not chunk)
   - Verify logs show chunking progress
   - Verify cleanup in /tmp

## Logging & Observability

Use logging.getLogger(__name__) so instance/request IDs attach automatically via existing logging setup.


**Key log points:**

```python
# Chunking decision
logger.info("Audio size %.1fMB exceeds threshold %.1fMB; chunking enabled", size, threshold)

# Silence detection
logger.debug("Detected %d silence points in %.1fs audio", len(points), duration)
logger.debug("Split at %.1fs (silence near ideal %.1fs)", split_point, ideal_time)

# Splitting
logger.info("Chunking audio: size=%.1fMB duration=%.1fs into %d chunks", size, dur, num)
logger.info("Audio chunked into %d pieces: %s", len(chunks), ", ".join(durations))

# Parallel processing
logger.info("Starting parallel transcription of %d chunks", len(chunks))
logger.debug("Chunk %d/%d complete: duration=%.1fs", i+1, total, chunk.duration)
logger.info("All chunks transcribed successfully in %.1fs", elapsed)

# Merging
logger.debug("Merging %d chunks with %d total segments", len(chunks), total_segments)
logger.info("Transcript merged: total_segments=%d duration=%.1fs", len(merged), duration)

# Cleanup
logger.debug("Cleaning up %d temporary chunk files", len(chunks))
```

## Performance Considerations

### Speed Comparison

**Current (single file):**
- Download: ~30s for 20 MB
- Upload to Whisper: ~10s
- Whisper processing: ~300s (10 min audio @ 0.5 RTF)
- **Total: ~340s (~5.7 min)**

**With chunking (3 chunks):**
- Download: ~30s for 20 MB (same)
- Split with ffmpeg: ~5s (stream copy, very fast)
- Upload 3 chunks in parallel: ~10s (same network speed)
- Whisper processing 3 chunks in parallel: ~100s (300s / 3)
- Merge: ~1s
- **Total: ~146s (~2.4 min)** -> ~2.3x faster

### Cost Considerations

- Whisper API charges per second of audio
- Chunking doesn't increase audio duration
- **Cost: Same** (same total audio seconds processed)
- May use more API requests but same total cost

### Resource Usage

- Temp disk space: ~file_size * 1.1 (during splitting)
- Memory: Minimal (streaming approach)
- Network: Same total bandwidth (parallel uploads)

## Rollout Plan

### Phase 1: Implementation (This PR)
- [ ] Implement AudioChunker with silence detection
- [ ] Implement ParallelTranscriber
- [ ] Implement TranscriptMerger
- [ ] Update STTTranscriptProvider to use chunking
- [ ] Add configuration options
- [ ] Add unit tests
- [ ] Add integration tests
- [ ] Update Dockerfile to include ffmpeg

### Phase 2: Deployment
- [ ] Deploy to Railway with ffmpeg
- [ ] Monitor logs for chunking behavior
- [ ] Test with real videos (manual testing)
- [ ] Verify temp file cleanup
- [ ] Monitor API costs

### Phase 3: Optimization (Future)
- [ ] Add overlap-based deduplication at chunk boundaries
- [ ] Tune silence detection parameters based on real data
- [ ] Add progress updates to Discord (e.g., "Processing chunk 3/5...")
- [ ] Add metrics (chunks per job, avg chunk size, etc.)
- [ ] Consider speaker diarization preservation across chunks

## Rollback Plan

If chunking causes issues:
1. Set `TRANSCRIPT_ENABLE_CHUNKING=false` in Railway
2. Bot will fall back to single-file transcription
3. 25 MB limit will apply again
4. No code changes needed

## Open Questions

1. **Should we add overlap between chunks?**
   - Pro: Reduces chance of missing words at boundaries
   - Con: Slightly more API cost, need deduplication
   - **Decision:** Not in v1, add in v2 if needed

2. **Should we show progress updates in Discord?**
   - Pro: Better UX for long jobs
   - Con: More complexity, Discord rate limits
   - **Decision:** Add logging first, consider Discord updates in v2

3. **What's the optimal silence threshold?**
   - Default: -40 dB (common value)
   - Consider: Make it configurable
   - **Decision:** Start with -40 dB, allow config override

4. **How to handle very short silence?**
   - Default: 0.5s minimum
   - Consider: Shorter may split mid-sentence
   - **Decision:** 0.5s is safe, allow config override

## Success Metrics

After implementation, track:
- [ ] % of jobs using chunking (expect ~30% for videos > 15 min)
- [ ] Average processing time improvement (expect ~2x faster)
- [ ] Chunking failure rate (expect < 1%)
- [ ] Temp file cleanup success rate (expect 100%)
- [ ] User errors related to file size (expect significant reduction)

## DRY Considerations

- Reuse shared types in `types.py` for segments and chunks.
- Keep ffmpeg/ffprobe invocation helpers localized to `chunker.py` to avoid leaking subprocess details.
- Avoid duplicating conversion helpers across modules; keep provider helpers in provider scope.

## References

- [OpenAI Whisper API Docs](https://platform.openai.com/docs/guides/speech-to-text)
- [ffmpeg silencedetect Documentation](https://ffmpeg.org/ffmpeg-filters.html#silencedetect)
- [ffmpeg segment/splitting](https://trac.ffmpeg.org/wiki/Seeking)
