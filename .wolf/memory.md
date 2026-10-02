# Memory

> Chronological action log. Hooks and AI append to this file automatically.
> Old sessions are consolidated by the daemon weekly.

## Session: 2026-10-02 21:47

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|

## Session: 2026-10-02 21:53

| Time | Action | File(s) | Outcome | ~Tokens |
|------|--------|---------|---------|--------|
| 21:57 | Created scripts/smoke.sh | — | ~889 |
| 21:57 | Edited scripts/smoke.sh | "--quickPlaySingleplayer \" → "--args=--quickPlaySinglep" | ~11 |
| 21:58 | Edited scripts/smoke.sh | 1→3 lines | ~59 |
| 21:59 | Edited scripts/smoke.sh | 1→4 lines | ~90 |
| 22:00 | added scripts/smoke.sh (runClient→quickplay→chat→um win shot→log check) using universal-modder `um` | scripts/smoke.sh | works, exit 0 | ~6k |
| 22:00 | Edited scripts/smoke.sh | expanded (+7 lines) | ~116 |
| 22:01 | Session end: 5 writes across 1 files (smoke.sh) | 1 reads | ~1248 tok |
| 22:03 | Edited build.gradle | expanded (+17 lines) | ~163 |
| 22:03 | Created scripts/mcproc.ps1 | — | ~440 |
| 22:04 | Created scripts/smoke.sh | — | ~1765 |
| 22:08 | Edited scripts/mcproc.ps1 | added 1 condition(s) | ~318 |
| 22:15 | smoke.sh → two clients on dedicated server; runSmokeServer/runSmokeListener in build.gradle; mcproc.ps1 | scripts/, build.gradle | passes, bubble visible | ~25k |
| 22:14 | Session end: 9 writes across 3 files (smoke.sh, build.gradle, mcproc.ps1) | 2 reads | ~4125 tok |
| 22:17 | TTS logs: 'TTS generated N chars in X ms' (worker) + 'TTS playing (spatial|mono)' after AL_PLAYING check; smoke.sh requires it on Listener | TtsPlaybackWorker.java, SpatialAudioPlayer.java, scripts/smoke.sh | smoke passes | ~5k |
| 22:17 | Session end: 9 writes across 3 files (smoke.sh, build.gradle, mcproc.ps1) | 2 reads | ~4125 tok |
| 23:25 | Session end: 9 writes across 3 files (smoke.sh, build.gradle, mcproc.ps1) | 2 reads | ~4125 tok |
| 23:26 | Session end: 9 writes across 3 files (smoke.sh, build.gradle, mcproc.ps1) | 2 reads | ~4125 tok |
| 23:26 | Session end: 9 writes across 3 files (smoke.sh, build.gradle, mcproc.ps1) | 2 reads | ~4125 tok |
| 23:28 | Session end: 9 writes across 3 files (smoke.sh, build.gradle, mcproc.ps1) | 2 reads | ~4125 tok |
| 23:28 | Session end: 9 writes across 3 files (smoke.sh, build.gradle, mcproc.ps1) | 2 reads | ~4125 tok |
| 23:31 | Session end: 9 writes across 3 files (smoke.sh, build.gradle, mcproc.ps1) | 2 reads | ~4125 tok |
| 23:45 | Created ../../AppData/Local/Temp/claude/C--Users-Mamoru-IdeaProjects-OmniChat/4cc00002-1812-45db-8003-6287882e197a/scratchpad/R.java | — | ~257 |
| 23:50 | code audit (workflow, 107 agents): 45 GH issues #1-#45 + tracking #46; fixed #1 path traversal, #13 sherpa speed, #29 HUD alpha, docs #39 #44 #45 | src, README.md, CLAUDE.md | smoke passes | ~6.3M subagent |
| 23:53 | Created .claude/worktrees/agent-ac8d0f57e82c4385c/src/main/java/org/mamoru/omnichat/network/VoiceRemoveS2CPayload.java | — | ~220 |
| 23:53 | Edited .claude/worktrees/agent-ae3d773eda8fd9747/src/client/java/org/mamoru/omnichat/client/tts/TtsEngine.java | added 1 import(s) | ~18 |
| 23:53 | Edited .claude/worktrees/agent-ae3d773eda8fd9747/src/client/java/org/mamoru/omnichat/client/tts/TtsEngine.java | 3→5 lines | ~30 |
| 23:53 | Edited .claude/worktrees/agent-ae3d773eda8fd9747/src/client/java/org/mamoru/omnichat/client/tts/TtsEngine.java | added 2 condition(s) | ~175 |
| 23:53 | Edited .claude/worktrees/agent-ae3d773eda8fd9747/src/client/java/org/mamoru/omnichat/client/tts/TtsEngine.java | added error handling | ~251 |
| 23:53 | Edited .claude/worktrees/agent-ae3d773eda8fd9747/src/client/java/org/mamoru/omnichat/client/tts/TtsEngine.java | inline fix | ~11 |
| 23:53 | Edited .claude/worktrees/agent-ae3d773eda8fd9747/README.md | 1→3 lines | ~118 |
| 23:53 | Edited .claude/worktrees/agent-ac8d0f57e82c4385c/src/main/java/org/mamoru/omnichat/server/ServerNetworkHandler.java | added 1 import(s) | ~26 |
| 23:53 | Edited .claude/worktrees/agent-ac8d0f57e82c4385c/src/main/java/org/mamoru/omnichat/server/ServerNetworkHandler.java | 5→2 lines | ~26 |
| 23:53 | Edited .claude/worktrees/agent-ac8d0f57e82c4385c/src/main/java/org/mamoru/omnichat/server/ServerNetworkHandler.java | added 2 condition(s) | ~243 |
| 23:53 | Edited .claude/worktrees/agent-ac8d0f57e82c4385c/src/main/java/org/mamoru/omnichat/Omnichat.java | 2→3 lines | ~37 |
| 23:53 | Edited .claude/worktrees/agent-ac8d0f57e82c4385c/src/main/java/org/mamoru/omnichat/Omnichat.java | added 1 condition(s) | ~82 |
| 23:53 | Edited .claude/worktrees/agent-ac8d0f57e82c4385c/src/client/java/org/mamoru/omnichat/client/network/ClientNetworkHandler.java | 2→3 lines | ~43 |
| 23:53 | Edited .claude/worktrees/agent-ac8d0f57e82c4385c/src/client/java/org/mamoru/omnichat/client/network/ClientNetworkHandler.java | modified onVoiceRemove() | ~92 |
| 23:53 | Edited .claude/worktrees/agent-ac8d0f57e82c4385c/src/client/java/org/mamoru/omnichat/client/network/VoiceCache.java | modified removeVoice() | ~38 |
| 23:54 | Created .claude/worktrees/agent-a73b32d2d676419b6/src/client/java/org/mamoru/omnichat/client/tts/TtsPlaybackWorker.java | — | ~1786 |
| 23:54 | Created ../../AppData/Local/Temp/claude/C--Users-Mamoru-IdeaProjects-OmniChat/4cc00002-1812-45db-8003-6287882e197a/scratchpad/edit_client.py | — | ~1278 |
| 23:54 | Edited .claude/worktrees/agent-a73b32d2d676419b6/src/client/java/org/mamoru/omnichat/client/tts/GladosTtsEngine.java | added 1 condition(s) | ~71 |
| 23:54 | Edited .claude/worktrees/agent-a73b32d2d676419b6/src/client/java/org/mamoru/omnichat/client/tts/GladosTtsEngine.java | 2→3 lines | ~17 |
| 23:55 | Edited .claude/worktrees/agent-a73b32d2d676419b6/src/client/java/org/mamoru/omnichat/client/tts/TtsEngine.java | added error handling | ~80 |
| 23:56 | Created .claude/worktrees/agent-a5a4e154da7781865/src/main/java/org/mamoru/omnichat/server/ModelTransfer.java | — | ~790 |
| 23:56 | Created .claude/worktrees/agent-a5a4e154da7781865/src/main/java/org/mamoru/omnichat/server/ModelFileServer.java | — | ~1980 |
| 23:56 | Edited .claude/worktrees/agent-a5a4e154da7781865/src/main/java/org/mamoru/omnichat/server/ServerNetworkHandler.java | 2→2 lines | ~35 |
| 23:56 | Edited .claude/worktrees/agent-a5a4e154da7781865/src/main/java/org/mamoru/omnichat/Omnichat.java | 1→3 lines | ~28 |
| 00:01 | fixed high issues #2 #3 #4 #5 #38 via 4 parallel worktree agents, merged, build+smoke pass | src/** | ok | ~300k |
| 00:01 | Created src/client/java/org/mamoru/omnichat/client/HearingRange.java | — | ~109 |
| 00:03 | Created .claude/worktrees/agent-a5d904f267503a752/src/main/java/org/mamoru/omnichat/server/VoiceStorage.java | — | ~1588 |
| 00:03 | Created .claude/worktrees/agent-a7cc3647b1bb950ce/src/client/java/org/mamoru/omnichat/client/tts/SherpaNatives.java | — | ~3111 |
| 00:03 | Created ../../AppData/Local/Temp/claude/C--Users-Mamoru-IdeaProjects-OmniChat/4cc00002-1812-45db-8003-6287882e197a/scratchpad/jp.sh | — | ~137 |
| 00:04 | Created .claude/worktrees/agent-aa981e6d544b0e574/src/client/java/org/mamoru/omnichat/client/tts/TtsService.java | — | ~2236 |
| 00:04 | Created ../../AppData/Local/Temp/claude/C--Users-Mamoru-IdeaProjects-OmniChat/4cc00002-1812-45db-8003-6287882e197a/scratchpad/jp.sh | — | ~288 |
| 00:04 | Edited .claude/worktrees/agent-a4e9cfddd757037e8/build.gradle | 4→9 lines | ~131 |
| 00:04 | Created .claude/worktrees/agent-a4a8aef936b1e70b5/src/main/java/org/mamoru/omnichat/network/ModelDownloadStatusS2CPayload.java | — | ~616 |
| 00:04 | Edited .claude/worktrees/agent-a4a8aef936b1e70b5/src/main/java/org/mamoru/omnichat/Omnichat.java | 2→3 lines | ~61 |
| 00:04 | Edited .claude/worktrees/agent-a4a8aef936b1e70b5/src/client/java/org/mamoru/omnichat/client/network/ClientNetworkHandler.java | 2→4 lines | ~61 |
| 00:04 | Edited .claude/worktrees/agent-a9045c2eac250265f/src/client/java/org/mamoru/omnichat/client/config/OmnichatConfig.java | modified type() | ~106 |
| 00:04 | Edited .claude/worktrees/agent-a9045c2eac250265f/src/client/java/org/mamoru/omnichat/client/config/OmnichatConfig.java | modified listAvailableModels() | ~339 |
| 00:04 | Created .claude/worktrees/agent-a9045c2eac250265f/src/client/java/org/mamoru/omnichat/client/chat/ChatPipeline.java | — | ~1381 |
| 00:05 | Created .claude/worktrees/agent-a524a0230060258fe/src/client/java/org/mamoru/omnichat/client/tts/SpatialAudioPlayer.java | — | ~3403 |
| 00:05 | Created .claude/worktrees/agent-a9045c2eac250265f/src/client/java/org/mamoru/omnichat/client/chat/ChatMessageHandler.java | — | ~497 |
| 00:05 | Edited .claude/worktrees/agent-a9045c2eac250265f/src/client/java/org/mamoru/omnichat/client/OmnichatClient.java | 2→2 lines | ~31 |
| 00:05 | Edited .claude/worktrees/agent-a9045c2eac250265f/src/client/java/org/mamoru/omnichat/client/OmnichatClient.java | — | ~0 |
| 00:05 | Edited .claude/worktrees/agent-a9045c2eac250265f/src/client/java/org/mamoru/omnichat/client/OmnichatClient.java | added 1 import(s) | ~30 |
| 00:05 | Created ../../AppData/Local/Temp/claude/C--Users-Mamoru-IdeaProjects-OmniChat/4cc00002-1812-45db-8003-6287882e197a/scratchpad/srv.py | — | ~2426 |
| 00:06 | Created .claude/worktrees/agent-a4a8aef936b1e70b5/src/client/java/org/mamoru/omnichat/client/network/ModelDownloadManager.java | — | ~4335 |
| 00:10 | medium issues #6-#12 #14-#21 via 7 parallel worktree agents; 1 merge conflict (OmnichatClient); jar 101→38 MB; smoke pass (voice sync on join verified: listener used 'irina') | src/**, build.gradle | ok | ~600k |
