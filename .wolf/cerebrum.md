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
