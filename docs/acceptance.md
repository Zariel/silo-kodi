# Initial release acceptance

Version `0.3.0` provides the planned browsing client for Kodi 21 on the tested CoreELEC setup. The original acceptance package matched the reproducible local ZIP and the downloaded GitHub CI artifact; subsequent browsing changes are described below. The supported workflows below have passed representative device checks, backed by 123 automated tests. The artifact is ready for local use and a GitHub prerelease; no release has been published as part of these checks.

All endpoints, fixture identities, account data, screenshots, and raw device results remain in ignored local testing storage. The [compatibility matrix](playback-references.md) records the scope of media/output evidence; [testing procedures](testing.md) describe reproduction and cleanup.

## Milestone results

| Milestone | Verified behavior | Evidence and limits |
| --- | --- | --- |
| Authentication | Manual server entry, production QR approval, persistent account/profile, masked PIN, profile switching, refresh and logout | Installed device login approved through Silo. Incorrect/correct PIN and profile isolation pass. Login survives package replacement and a Kodi service restart. Real logout revokes a separate test session while preserving the installed session. Synthetic client expiry triggers real renewal during original and HLS playback; deterministic tests cover polling/error/retry contracts. |
| Browsing | Viewer libraries, cursor pages, movie/series details, seasons/episodes, remote focus and rounded Silo-style surfaces | Real catalog pages and expanded Home sections, details/back navigation, profile switching, and server accent pass. An injected connection failure is retryable from the sidebar. Missing artwork retains readable, selectable cards. No Kodi catalog synchronization or local catalog database. |
| Basic playback | Movies and episodes through authorized streams, progress/heartbeats, cleanup | Real playback runs beyond the idle-heartbeat window; independent Silo reads verify saved progress. Failed-start, replacement, transient progress failures, and lost committed replies are exercised. Owned sessions and streams are closed without stopping unrelated replacement playback. |
| Full playback | Pause/resume, seeking, server resume/start-over, native audio selection, representative HDR/DV/lossless-audio paths | Observed player clocks and server watch state establish resume/restart and seeking. Driver/HDMI observations establish HDR10 and DV output; the playback overlay reports profile 7 FEL with hardware decoding. Receiver reads confirm TrueHD/Atmos and DTS-HD MA, including pause/seek/resume. A 606-second high-bitrate window passes sampled clock/cache checks. These are scoped device measurements, not universal codec, picture-quality, or maximum-bitrate claims. |
| Quality and subtitles | Server-offered quality selection, text and embedded PGS, Off, original/HLS transitions | All six offered SDR choices for the test source pass decoded-height, pause, resume, seek, and Auto checks. WebVTT and native PGS cues are visually checked; PGS burn-in is checked in lower-quality HLS. Audio selection survives representative transitions. Stop, replacement, renewal, and lost committed replan replies pass. |
| Silo Home | Main page, server layout and accent, sections/View all, progress refresh and profile isolation | Home follows server-provided ordering and IDs. Aggregate and profile-settings fallback paths pass injected-compatibility checks. Continue Watching updates after playback in the same window. Default recipe ordering is used only for discovered settings without positions. |

## Packaging and repository checks

- The package contains the add-on allowlist and required license notices, excluding test configuration, credentials, source snapshots, and generated Python caches.
- Identical inputs produce identical ZIP bytes. The SHA-256 sidecar is verified, a matching release tag builds, and a mismatched tag leaves the existing artifact unchanged.
- For the original acceptance build, independent hashes of installed files matched the local ZIP and the successful [GitHub CI artifact](https://github.com/Zariel/silo-kodi/actions/runs/40118604371).
- Kodi's ZIP installer replaces the package without changing saved credentials. An isolated empty data directory opens manual server setup without inheriting an account.
- Repository guidance and ignored scratch/testing directories are present. Known private deployment references were absent from the tracked tree and all 64 reachable revisions inspected before the final documentation changes.
- The [GitHub Release procedure](releases.md) and release-triggered asset workflow are configured. CI artifact creation is verified; actual release publication and asset attachment remain the publisher's step.

## Automatic paging and compact navigation follow-up

Library and expanded Home grids preload cursor pages without a **Load more** card. The local suite covers overlap deduplication, filtered empty pages, repeated cursors, failure recovery, stale navigation results, and profile authority. A device check observed a library grow from 100 to 150 cards without a loading banner and retain the selected card through details and Back.

The sidebar collapses to icons when content has focus and expands its labels when navigation regains focus. Captures verify both layouts, but some icons intermittently disappear after changing libraries. This remains unresolved. Expanded Home automatic paging, exact viewport placement during a background append, and final sidebar rendering still need device acceptance. Target checks resumed with the receiver showing another input. The browsing/navigation build is deployed; it has not been requalified against the original GitHub artifact.

## Playback navigation follow-up

The Now playing sidebar destination is removed. A short device check using the installed browser and a real episode verified Back from fullscreen to the originating collection, preservation of the selected title and player identity, opening Quality through the context menu, and Back returning to the same fullscreen player. The owned video stopped and the test window closed normally. Local tests cover navigation history, profile-bound playback metadata, menu access, and cleanup. This test ran with the receiver on another input and does not add HDMI or audible-output evidence.

## Known limitations

- Original media is presented by Kodi. HDR, DV/FEL, passthrough, and supported bitrates depend on the Kodi build, hardware, and configuration. The DV capture path cannot independently prove physical picture quality; no frame-perfect or universal FEL guarantee is made. Audible speaker-output quality was not measured by the automation.
- The qualified transcoded path is SDR H.264/AAC HLS. Progressive remux, anchored/live/variant or encrypted HLS, cross-origin authenticated media, and other transcode combinations are not supported by this initial executor.
- Use Silo's subtitle menu for negotiated changes. Direct Kodi subtitle OSD selections are not reconciled into later Silo replans. ASS styling/fonts, other bitmap formats, SRT device qualification, and remembered-choice editing remain future work.
- Ambiguous native track metadata is rejected rather than guessing. Multipart chaining and library-specific presentation context are not implemented.
- Extended media-network outages, untested media variants, and broader peak-bitrate/render-quality coverage remain unqualified. Synthetic expiry is the repeatable renewal gate; waiting for natural wall-clock expiry is optional additional coverage.
- Releases are manually installed ZIPs. A Kodi repository feed for automatic updates, standalone music, offline downloads, discovery, catalog synchronization, and full mobile-client feature parity are outside this initial client.
