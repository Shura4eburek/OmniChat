# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-05-09

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->

## Key Learnings

- **Project:** OmniChat
- **Description:** Fabric мод для Minecraft, добавляющий голосовую озвучку чата (TTS) с пространственным звуком и визуальные облачка сообщений над головами игроков.

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->

- [2026-10-02] Smoke test: `scripts/smoke.sh` (needs universal-modder `um` + one-time `um win setup`). Dev client's authlib 401 / Realms errors are normal offline noise.
- [2026-10-02] Do-Not-Repeat: this project's `gradlew` does `eval set -- ... "$@"`, so args with spaces get re-split; escape them with `printf '%q'` before passing (e.g. `--args=--quickPlaySingleplayer "New World"`).
- [2026-10-02] um WinDrive `type` mangles Cyrillic (OEM codepage); smoke.sh pastes non-ASCII via clipboard.
- [2026-10-02] smoke.sh is now 2-client: runSmokeServer (run/smoke/server, offline flat, port 25599, Speaker op) + runClient as Speaker + runSmokeListener (run/smoke/listener); models shared via junctions. Pick game processes by `dli.env=client|server` in java cmdline, not by username (gradlew wrapper matches too).
- [2026-10-02] Decision: user chose a second client (not F5) to verify chat bubbles/TTS from another player's view.
- [2026-10-02] TTS logging never includes message text (chat can be private) — only length, model, speaker, timing.
- [2026-10-02] Audit backlog lives in GitHub issues labelled 'audit' (tracking issue #46 has the structure report). sherpa-onnx OfflineTts.generate speed arg already means faster>1 — don't invert it.
- [2026-10-03] TTS engines are owned by TtsPlaybackWorker (load/cache/release on its thread); OmnichatClient.loadEngineForModel returns null on failure — never cache fallbacks. Catch LinkageError around native engine creation.
- [2026-10-03] Model transfers: static scheduler in ModelFileServer, registered ONCE in onInitialize (Fabric events can't be unregistered; SERVER_STARTED fires per world on integrated server). 2 chunks/tick/transfer, 2 global transfers. No public connection-open check in Yarn 1.21.11 → use player.isDisconnected().
- [2026-10-03] Parallel fixes via worktree subagents worked well when file ownership was split explicitly in prompts.
- [2026-10-03] Client TTS lives in tts/TtsService (async loader thread "OmniChat-TTS-Loader"); chat goes through chat/ChatPipeline (single CHAT listener, HearingRange.BLOCKS=40). Spatial audio: AL_LINEAR_DISTANCE_CLAMPED, per-sender queue, SoundEngineMixin drops AL objects on SoundEngine.close.
- [2026-10-03] Model downloads: ModelDownloadStatusS2CPayload (QUEUED/FAILED), client writes to config/omnichat/downloads/<name>.part and installs atomically; sherpa natives cached in config/omnichat/natives/win-x64-<hash>.
- [2026-10-03] After editing jar excludes in build.gradle, Gradle may keep :jar UP-TO-DATE — run `./gradlew clean build`.
- [2026-10-03] sherpa natives no longer ship onnxruntime.dll: SherpaNatives loads ORT 1.19.2 (OrtEnvironment) first, sherpa binds to it. Don't re-add the bundled 1.17.1 DLL.
- [2026-10-03] Fabric C2SPlayChannelEvents.REGISTER can fire in the configuration phase (before JOIN): never send play payloads from it unless JOIN already happened. Built jar can be tested with ./gradlew prodClient (run/prod).
