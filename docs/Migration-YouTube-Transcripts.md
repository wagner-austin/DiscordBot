# Migration: YouTube Transcripts

Summary of transcript approaches and guidance.

## Options

- Captions (default)
  - Uses `youtube-transcript-api` to fetch auto/community captions when available.
  - Clear user messages when unavailable/blocked.

- STT (Speech-to-Text)
  - Enable via `TRANSCRIPT_PROVIDER=stt` and set `OPENAI_API_KEY`.
  - Preflight checks use `yt_dlp` probe to estimate duration and size; blocks early if limits exceeded.
  - Audio download + Whisper transcription; users are DM’d on failure (no silent waits).

## Configuration

- `TRANSCRIPT_PROVIDER` — `youtube` (default) or `stt`
- `OPENAI_API_KEY` — required for STT
- `TRANSCRIPT_MAX_VIDEO_SECONDS` — duration limit for STT (default 5400)
- `TRANSCRIPT_MAX_FILE_MB` — audio size limit for STT (default 25)
- `TRANSCRIPT_PREFERRED_LANGS` — caption languages preference (default `en,en-US,en-GB`)
 - `TRANSCRIPT_COOKIES_TEXT` — optional `Cookie` header for YouTube requests (STT only)
 - `TRANSCRIPT_COOKIES_PATH` — optional path to a `cookies.txt` (Netscape) file for YouTube (STT only)

## Reliability Notes

- YouTube may block certain environments from fetching captions; STT is a reliable alternative.
- Production environments can have different outcomes than local; prefer the pinned Poetry lock for consistency.

See also: `docs/README.md#features` and `docs/Background-Jobs.md`.
