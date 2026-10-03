# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-05-09

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->

## Key Learnings
- omnivoice: install-omnivoice.bat is UTF-8 without BOM + CRLF with `chcp 65001 >nul` on line 2; dry-run via `OMNIVOICE_DRYRUN=1 cmd /c` to verify parsing.
- omnivoice: no host nvidia-smi => deps.check_all marks WSL/ENV optional; ui needs_setup is False when env.gpu_name is None.
- omnivoice (tools/omnivoice): piper fine-tune `--ckpt_path` restores base loop state; irina base is epoch 4139 → `--epochs` is ADDITIONAL epochs; Lightning ckpt `epoch=N` is 0-based.
- `uv sync --extra X` removes other extras — always `uv sync --all-extras`. sherpa-onnx wheel needs `sherpa-onnx-core` or it loads System32 onnxruntime 1.17 and crashes.

- **Project:** OmniChat
- **Description:** Fabric мод для Minecraft, добавляющий голосовую озвучку чата (TTS) с пространственным звуком и визуальные облачка сообщений над головами игроков.

## Do-Not-Repeat
- 2026-10-03: don't bump wslenv.ENV_VERSION for cosmetic wsl_setup.sh edits (e.g. apt cleanup) — it re-provisions every user's distro.
- 2026-10-03: a long python heredoc with nested ''' and quotes broke Git Bash parsing; write edit scripts to the scratchpad with Write and run them.
- [2026-10-03] Haiku implementers ignored trailer/.wolf staging rules — use sonnet+ for implementer subagents.

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->

## Decision Log

- [2026-10-03] omnivoice WSL: wsl.exe own output is UTF-16LE (in-distro command output is UTF-8) — use wslenv.decode. Rootfs pin = releases.ubuntu.com/24.04.5 .wsl (gzip tar) sha bb415d82…; in-distro commands via wslenv.wsl_cmd (-u root). Downloads go through omnivoice/download.fetch. core.autocrlf=true → tools/omnivoice/.gitattributes forces LF for *.sh.

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
- [2026-10-03] Manual UI testing: um WinDrive targets the FIRST java window — close other clients first. Settings screen overflows at 854x480 auto GUI scale (#47); use guiScale:1 in run/smoke/listener/options.txt for UI tests. Remove junctions with cmd rmdir (no /s) — never rm -rf a junction.
- [2026-10-03] Decision: UI redesign = teal (#35E0C8) "tactical HUD" pixel style (user's reference image), own widgets on vanilla ClickableWidget (no owo/YACL), voice.json + portrait.png metadata with generated fallback portraits, protocol v2 VoiceCatalogS2CPayload. Spec docs/superpowers/specs/2026-10-03-pixel-hud-ui-design.md, plan docs/superpowers/plans/2026-10-03-pixel-hud-ui.md, epic #59. Sub-project 2 (in-world visuals) not designed yet.
- [2026-10-03] User preference: target audience = Modrinth publication, wants the mod to stand out visually; likes to plan today, implement next day; wants GitHub issues for planned work.
- [2026-10-03] 1.21.11 Yarn UI API: ClickableWidget.renderWidget/onClick(Click,boolean)/keyPressed(KeyInput)/isValidClickButton(MouseInput); PressableWidget.renderWidget is final (subclass ClickableWidget for custom looks); SliderWidget.renderWidget is overridable; drawTexture(RenderPipelines.GUI_TEXTURED, id, x, y, u, v, w, h, texW, texH); javap at "C:\Program Files\Java\jdk-25\bin\javap.exe".
- [2026-10-03] Brainstorm companion server: Windows reserves many high ports (EACCES) — start with BRAINSTORM_PORT=47823.
- [2026-10-04] Pixel HUD UI implemented on branch feat/pixel-hud-ui (SDD: 11 tasks + final review fix wave). Client UI lives in client/ui (screen/, widget/); Voice tab rebuild trigger = VoiceCatalog.signature (no progress), live progress via Supplier; OmnichatScreen.rebuild preserves focus.
- [2026-10-04] Do-Not-Repeat: Agent-tool isolation worktrees are created from main/HEAD at spawn time, not from the current feature branch — parallel worktree agents re-added JUnit; cherry-pick their Java files without build.gradle, or tell them to merge the feature branch first.
- [2026-10-04] Smoke listener options: tutorialStep none, pauseOnLostFocus false (set by scripts/smoke.sh).
- [2026-10-04] sherpa-onnx piper models MUST have 'voice' (+has_espeak) metadata or generate() throws a native exception that kills the JVM; TtsEngine validates via OnnxMetadata. Local 'glados' model lacks it (fix: add voice=ru with onnx python).
- [2026-10-04] omnivoice train.py: backends DOCKER/WSL (train.BACKENDS) build commands; one shared _fit_loop. Env.backend "wsl"|"docker"|None; Env without backend + docker+gpu = docker (legacy). UI Stop → train.stop_training(p) which uses train._ACTIVE (set while train_project runs).
- (2026-10-03) omnivoice CLI: `typer.Exit` subclasses RuntimeError — never `raise typer.Exit` inside a `try/except RuntimeError`; compute an exit code and raise after.
- (2026-10-03) omnivoice UI: global CSS class `.bad` = red + line-through (phrases table); don't reuse it for other rows (use e.g. `miss`). 1 s gr.Timer ticks need `show_progress="hidden"` or outputs flash a "queue" overlay.
- (2026-10-03) .bat dry runs: `echo` keeps the previous errorlevel, so guard checks after `%RUN%` commands with `if not defined RUN`.

- [2026-10-03] Git Bash `sed -i` strips CRLF on Windows: edit CRLF files (.bat) with Python in binary mode.
- [2026-10-03] Python heredoc strings: `` in Windows paths (fmpeg) becomes a form feed - use raw strings for paths.
