# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-05-09

## User Preferences
- [2026-10-04] The user plays through Modrinth App (profile «123123» has omnichat-0.1.jar); also has CurseForge and .minecraft installed.
- [2026-10-04] Phrases page: likes the bottom «Выбранная фраза» gr.Audio player as is; list must be cards (▶, track name, editable text, ✕), not a table.
- [2026-10-04] User expects UI changes to be visually inspected before reporting ("ты смотришь вообще, как оно выглядит?"): zoom in on the changed component, test narrow widths, no native/browser-default widgets that break the HUD style.
- [2026-10-04] Tables that the user should not edit must not look editable; for file lists prefer cards with play + delete. Destructive/creating flows (new project, delete project) are full pages opened from sidebar buttons, not sidebar accordions.
- [2026-10-04] Dislikes long dropdowns for choosing among many items — prefers a separate tab with a sortable table.

<!-- How the user likes things done. Code style, tools, patterns, communication. -->

## Key Learnings
- omnivoice packs export/model.onnx; export_project writes export/model.json (checkpoint, epoch from base, mos, mel, time) — train.model_info: None = not exported, {} = unknown origin (old export / onnx newer than note). Shown on «Упаковка» and as «экспортирован» chip on checkpoint cards. HTML-only buttons switch sections by clicking the hidden sidebar radio input (theme.HEAD).
- Gradio 6: setting a hidden Textbox's textarea value + dispatching a DOM 'input' event fires the component's .change (not .input) — used for clickable HTML cards (#ckpt-pick). Lists refreshed by a timer are better as one gr.HTML than gr.render (no component re-creation / flicker). helpers.hud_player_html is the shared HUD audio player.
- omnivoice training runs omnivoice/piper_compat/fit.py (WSL: via /mnt/c path, no re-setup; Docker: compat dir mounted at /omnivoice_compat) instead of `-m piper.train`; Colab still uses piper's CLI (fit_args script=None). Stop is graceful via <train>/STOP; pkill pattern 'piper_compat/fit.py|piper.train'. Lightning 2.6.6 saves last.ckpt only when a top-k save happens; resume creates a new lightning_logs/version_N.
- To test the WSL env from Git Bash, write a .sh into the scratchpad and run `wsl.exe -d omnivoice -- bash /mnt/c/...` via PowerShell (inline quoting breaks).
- Gradio 6 field DOM: Number = label.container > input; Textbox = label.container > .input-container > input; Dropdown frame = .wrap around input[role=combobox] (40px). omnivoice forces single-line inputs to 40px and pins them to the bottom of their block so wrapped labels don't misalign rows; number spin arrows hidden.
- omnivoice spacing: Gradio pads HTML blocks 12px left/right (now 0 in .hud-section) and 10px top/bottom; a gr.Row with all children hidden has only comment nodes (use :not(:has(*)), not :empty). Measure gaps with getBoundingClientRect; target 20px between stacked blocks. Fake training charts for UI checks: tests.test_previews.piper_events into <project>/train/lightning_logs/version_0.
- Gradio 6: a .click() with js="(...a)=>{...; return a;}" runs front-end code before the handler while keeping one dependency (tests look up deps by button). Native <audio src="gradio_api/file=<abs>"> works for files in allowed_paths. gr.render(inputs=[...]) + a gr.State revision counter re-renders dynamic lists.
- Piper voice samples: https://huggingface.co/rhasspy/piper-voices/resolve/main/<lang>/<loc>/<voice>/<quality>/samples/speaker_0.mp3; checkpoints in dataset rhasspy/piper-checkpoints (some named voice-NNNN.ckpt without epoch= — avoid, base_epoch needs it).
- Piper base models in languages.BASE_CHECKPOINTS (ru: denis/dmitri/ruslan male, irina female — the ru default). Project Arthas was trained from irina (female) → quality ceiling; male voices should start from a male base.
- omnivoice UI: every UPPERCASE name in ui/strings.py must be a plain str (test_strings_have_no_empty_values) — tuples/lists go in helpers.py. «Чекпойнты» is a NAV section (not a project step) mapped to step "train". Gradio 6 Dataframe cells are div gridcells (no tr/td) and virtualised.
- Gradio 6 Dropdown filters options on keyup of ANY non-nav key (even Shift) by the input text; omnivoice swallows such keys in theme.HEAD. Default Project base checkpoint = epoch 4139 (tests must use epochs relative to it).
- Checkpoint list: warm-up epochs (max(20, 5%) after base) are hidden and never ★ — early MOS is inflated because the voice is still the base one.
- omnivoice UI logs use elem_classes="log-box" + JS in theme.HEAD for stick-to-bottom/↓ button (Gradio autoscroll fails on full value rewrites).
- [2026-10-04] omnivoice piper events: audio clips (tag = phrase text) use global_step, val_* scalars + "epoch" use Lightning's own step — a clip belongs to the NEXT "epoch" scalar in file order. tensorboard's pure-python reader takes ~4 s/30 MB; previews._EventFile reads TFRecords itself incrementally (byte offset, ~0.16 s). Epoch scalar value == checkpoint epoch=N (absolute; new = N - base_epoch).
- [2026-10-04] omnivoice training UI: TrainRunner keeps trainlog.LogCleaner (clean log) + raw train/train.log; Lightning prints nothing on checkpoint save, runner.poll_checkpoints diffs the dir. val_mos (UTMOS) is highest at the first epochs (base voice) — "best by MOS" can be near-base.
- omnivoice: install-omnivoice.bat is UTF-8 without BOM + CRLF with `chcp 65001 >nul` on line 2; dry-run via `OMNIVOICE_DRYRUN=1 cmd /c` to verify parsing.
- omnivoice: no host nvidia-smi => deps.check_all marks WSL/ENV optional; ui needs_setup is False when env.gpu_name is None.
- omnivoice (tools/omnivoice): piper fine-tune `--ckpt_path` restores base loop state; irina base is epoch 4139 → `--epochs` is ADDITIONAL epochs; Lightning ckpt `epoch=N` is 0-based.
- `uv sync --extra X` removes other extras — always `uv sync --all-extras`. sherpa-onnx wheel needs `sherpa-onnx-core` or it loads System32 onnxruntime 1.17 and crashes.

- **Project:** OmniChat
- **Description:** Fabric мод для Minecraft, добавляющий голосовую озвучку чата (TTS) с пространственным звуком и визуальные облачка сообщений над головами игроков.

- omnivoice synthetic data (issue #60): synth.py (synth/synth.json, lines.txt, wavs/), corpus.py (bundled CC0 corpus_ru.txt), synth_check.py (Whisper verdicts), teacher.py (XttsTeacher → piper_compat/xtts_gen.py in WSL venv /opt/omnivoice/xtts, STOP file + 60 s grace), ui SynthRunner. Training: dataset.piper_csv repeats originals ×weight, train.build_audio_dir hardlinks segments + accepted synth wavs into train/audio. «Синтетика» is OPTIONAL_STEPS — never blocks steps / first_open_section.
- Gradio test helper _handler(demo, name) finds handlers among REGISTERED event fns only — a plain helper must be wired to some event (e.g. State.change) to be testable that way.
- wslenv.xtts_ready() asks WSL (seconds): cache it for timer ticks (app.xtts_ok), call fresh once per page view.
## Do-Not-Repeat
- [2026-10-05] The user's live omnivoice UI must NOT run as a Claude Code background task: under memory pressure Claude Code reaps idle background shells, killing the UI and the training it drives (lost a run at epoch 2489). Tell the user to start it in their own terminal. Before claiming "training was not running", check checkpoint/log mtimes, not only pgrep after the fact. A failed background start can hide behind an old UI still holding port 7860 — verify the served version.
- [2026-10-04] Visual check of filtered card lists: walk every item state through every action and confirm it stays reachable in SOME filter (a manually dropped «спорная» vanished from all filters until «Брак» included manual drops).
- [2026-10-04] Killing a background `omnivoice ui` by its port owner can leave the launcher holding the port — kill every process whose CommandLine contains `--port 7861` (not bash.exe).
- [2026-10-04] Never run bare `python -` from the Bash tool on this machine: it hangs (Store alias). Use tools/omnivoice/.venv/Scripts/python with a script file.
- [2026-10-04] Don't draw composite icons (arrows on arcs) with CSS borders — use an SVG data-URI as mask-image (theme.UNDO_SVG); Gradio keeps url("data:…") intact. Inspect every icon at 6x zoom, not just layout.
- [2026-10-04] Gradio's CSS rewrite DROPS a `border:` shorthand that is followed by a border longhand in the same rule — use border-width/style/color longhands. Icons on gr.Button: label text stays in the button (font-size:0) and is a grid/flex item → centre pseudo-icons with position:absolute; inset:0; margin:auto.
- [2026-10-04] UI review checklist before reporting: 1x and 3-4x zoom; idle/hover/focus/active/playing states; neighbours aligned (compare getBoundingClientRect mids); nothing clipped by overflow:hidden; icons centred with grid not pixel offsets; global box-sizing:border-box affects pseudo-element icons.
- [2026-10-04] Don't ship native <audio controls> / browser-default widgets in omnivoice UI — use the HUD .rp player (theme.HEAD + CSS). Always zoom-check new components (body.style.zoom=2) for overflow before reporting.
- [2026-10-04] The Bash tool here mangles backslashes inside heredocs (\n -> real newline) — write Python strings with 
 via the Edit tool, not heredoc scripts.
- [2026-10-04] Gradio file outputs outside cwd/temp need allowed_paths in launch() (failure is only in server log, not toasted).
- [2026-10-04] Gradio: two handlers on one event writing the same output with a stale input (e.g. section) race — give each output one owner. elem_classes on gr.Radio lands on the <fieldset> itself (use fieldset.cls, not .cls fieldset).
- [2026-10-04] Silkscreen font has NO Cyrillic — use it only for Latin-only text (logo); Russian UI text in JetBrains Mono.
- [2026-10-04] Don't restart the omnivoice UI while training runs: piper is a child Popen of the UI process and dies with it. Old UI python may linger on :7860 (base uv cpython PID) — kill it too.
- [2026-10-04] Git Bash heredocs (even quoted 'EOF') can lose backslashes in Windows paths written into .py files - use the Edit/Write tools for any line containing a backslash.
- 2026-10-03: don't bump wslenv.ENV_VERSION for cosmetic wsl_setup.sh edits (e.g. apt cleanup) — it re-provisions every user's distro.
- 2026-10-03: a long python heredoc with nested ''' and quotes broke Git Bash parsing; write edit scripts to the scratchpad with Write and run them.
- [2026-10-03] Haiku implementers ignored trailer/.wolf staging rules — use sonnet+ for implementer subagents.

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->

## Decision Log
- [2026-10-04] Checkpointing: one best per metric + last.ckpt every 10 epochs (user chose option 1 over moving checkpoints to the WSL disk).
- [2026-10-04] Synthetic-data training (XTTS v2 / F5-TTS teacher) deferred → GitHub issue #60.

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

- [2026-10-04] omnivoice dependency folder: paths.cache_source() = OMNIVOICE_CACHE env > data_dir in %APPDATA%\omnivoice\config.json > %LOCALAPPDATA%\omnivoice. datadir.move_data moves it (wsl --manage --move first, then copy+size check, config switch, delete). UI reuses SetupRunner.start(job=, done_text=, error_title=).
- [2026-10-04] omnivoice slicing is transcript-driven: slicer._plan_words -> faster-whisper words (vad_filter, word_timestamps) -> segments.plan_from_words (sentence split, merge only too-short pieces, energy snap of cuts) + re-recognition of uncovered loud spans. Whisper (esp. with VAD) skips lines and mistimes words near chunk edges by up to ~0.6 s — never trust raw word timestamps for cuts. Silero path = fallback only without faster_whisper.
- [2026-10-04] Decision: merging "short sentences" (<2 s) put several unrelated game lines into one clip; merge only pieces whose clip would be < 1 s (span + 2*0.15 pad). Word-path `check` uses no_speech > 0.6 (0.5 flagged clean lines).
- [2026-10-04] This PC: ctranslate2 sees the GPU but cublas64_12.dll is missing -> Whisper runs on CPU (medium); transcriber._cuda_libs_missing detects it. Gradio 6: restrict progress with `show_progress_on=[component]`.
