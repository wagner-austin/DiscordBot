Deploying to Railway

Overview
- This project requires two processes when TRANSCRIPT_PROVIDER=stt:
  - bot: the Discord bot process
  - worker: an RQ worker that processes the "transcript" queue and publishes events
- Both processes need access to the same Redis instance via REDIS_URL.

Quick setup
1) Create a new Railway project from this repo.
2) Ensure Redis plugin is added (railway.json includes it). Railway will inject REDIS_URL.
3) Two services are defined:
   - bot: start command python -m src.clubbot.main
   - worker: start command poetry run rq worker transcript --with-scheduler
4) Required environment variables:
   - bot: DISCORD_TOKEN, TRANSCRIPT_PROVIDER=stt, OPENAI_API_KEY, REDIS_URL
   - worker: TRANSCRIPT_PROVIDER=stt, OPENAI_API_KEY, REDIS_URL

Notes
- If you disable STT (TRANSCRIPT_PROVIDER=youtube), you do not need the worker.
- The Dockerfile builds all dependencies including Poetry and ffmpeg (for chunking).
- The repo also contains a Procfile declaring bot and worker, which Railway can detect.

