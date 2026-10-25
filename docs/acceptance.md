# Initial release acceptance

Version `0.3.0` provides the planned browsing client for Kodi 21 on the tested CoreELEC setup. The original acceptance package matched the reproducible local ZIP and the downloaded GitHub CI artifact; subsequent browsing changes are described below. The supported workflows below have passed representative device checks, backed by 130 automated tests. The artifact is ready for local use and a GitHub prerelease; no release has been published as part of these checks.

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

The sidebar collapses to icons when content has focus and expands its labels when navigation regains focus. The denser browsing follow-up below verifies the revised rail. Expanded Home automatic paging and exact viewport placement during a background append still need device acceptance. Target checks resumed with the receiver showing another input. The browsing/navigation build is deployed; it has not been requalified against the original GitHub artifact.

## Playback navigation follow-up

The Now playing sidebar destination is removed. A short device check using the installed browser and a real episode verified Back from fullscreen to the originating collection, preservation of the selected title and player identity, opening Quality through the context menu, and Back returning to the same fullscreen player. The owned video stopped and the test window closed normally. Local tests cover navigation history, profile-bound playback metadata, menu access, and cleanup. This test ran with the receiver on another input and does not add HDMI or audible-output evidence.

## Denser browsing, search, and title actions

The library and search grid now shows eight columns and three rows on the 1080p design canvas. Kodi scales that canvas to the configured GUI resolution. Home retains two horizontal shelves; film and TV details use tighter text and action spacing. The sidebar expands over stationary content. Repeated Home/library focus transitions pass. Some captures show all rail icons, while others omit unchanged rail elements. Kodi’s GLES screenshot path renders dirty regions before reading the backbuffer, so these captures do not distinguish a screenshot artifact from an on-screen fault. Physical visual confirmation remains outstanding; no frame-time benchmark was performed. Physical 4K GUI rendering remains untested.

The [official TV client review](tv-client-references.md) informed search and card actions. Device checks verify native keyboard search, title options, details/Back selection, TV/season/episode details, and search paging from 100 to 150 results without a Load more control. A favourite was toggled through the title menu, independently checked through the favourite endpoint, and restored to its original state. Watched and watchlist endpoint contracts are covered locally; real watch history was not changed. A physical remote hold still depends on its Kodi keymap; the context-menu action itself is verified.

The local suite passes 130 tests. The installed package passed SHA-256 verification. Checks ran with the receiver on another input, with no playback started, and ended with idle display protection verified. These checks do not add HDMI-output evidence or requalify the original CI artifact.

## Known limitations

- Original media is presented by Kodi. HDR, DV/FEL, passthrough, and supported bitrates depend on the Kodi build, hardware, and configuration. The DV capture path cannot independently prove physical picture quality; no frame-perfect or universal FEL guarantee is made. Audible speaker-output quality was not measured by the automation.
- The qualified transcoded path is SDR H.264/AAC HLS. Progressive remux, anchored/live/variant or encrypted HLS, cross-origin authenticated media, and other transcode combinations are not supported by this initial executor.
- Use Silo's subtitle menu for negotiated changes. Direct Kodi subtitle OSD selections are not reconciled into later Silo replans. ASS styling/fonts, other bitmap formats, SRT device qualification, and remembered-choice editing remain future work.
- Ambiguous native track metadata is rejected rather than guessing. Multipart chaining and library-specific presentation context are not implemented.
- Extended media-network outages, untested media variants, and broader peak-bitrate/render-quality coverage remain unqualified. Synthetic expiry is the repeatable renewal gate; waiting for natural wall-clock expiry is optional additional coverage.
- Releases are manually installed ZIPs. A Kodi repository feed for automatic updates, standalone music, offline downloads, discovery, catalog synchronization, and full mobile-client feature parity are outside this initial client.

## TV title actions

The installed add-on opens its title menu through Kodi's synthetic held-Enter input (`Input.ButtonEvent`, keyboard map, 1000 ms). Cancel leaves playback stopped and Home unchanged. Removing a movie from Continue Watching removes it from the displayed shelf and an independent server section read; the test then undismisses it and verifies membership is restored. Favourite add/remove is verified through the independent favourites endpoint, with original state and selection restored. Both checks end with idle display protection.

The automated suite passes 135 tests, including dismissal anchors, profile ownership, menu targeting, and rejection of an older in-flight page after Home membership changes. Next Up and whole-show dismissal have contract coverage but were not mutated on the user's profile. Physical remote hold behaviour still depends on its Kodi key mapping.

## Home loading and sidebar focus

A device trace reproduced sidebar focus in 27 of 60 samples while scrolling downward through Home shelves without Left input. Home now fetches replacement shelves before clearing controls and binds each complete list in a batch. The same check records zero sidebar jumps in 60 samples. Home starts expanded; Down enters the cards, and Left restores normal sidebar navigation.

A temporary wrapper delays the first Home request by six seconds while using the installed browser and real catalog. Down during that delay enters the cards when loading completes. Subsequent sidebar navigation and Right into the cards pass. The wrapper closes normally and idle protection is verified. The automated suite passes 142 tests, covering initial directions, explicit Left, deferred focus, failed fetches, and visible shelves during refresh.

## Partial rows as scroll cues

Framebuffer captures from the installed add-on show two complete Home shelves plus the next shelf's heading and clipped artwork, three complete grid rows plus part of the fourth, and three complete episode entries plus part of the fourth. Navigating down promotes the Home preview to the second full shelf and retains card focus. Grid row navigation and TV/season/episode details pass without playback, followed by verified idle protection. Automated tests cover skipping empty shelves and clearing the preview at the end; all 144 tests pass.

## Home preload and horizontal continuation

Home resolves all section cards before rendering and retains them while navigating vertically. The installed browser passes Home preview promotion and library navigation with this preload. A temporary read-only Home fixture uses real catalog pages as a large Continue Watching shelf: automatic paging grows it from 100 to 150 cards without a View all entry or a selection change. A counter independently confirms that vertical navigation invokes Home preload only once. No playback or personal-state mutation is needed; the wrapper closes normally and idle protection is verified.

The shared paging contract covers grids and Home shelves, including duplicate IDs, repeated cursors, profile ownership, replaced shelves, and reassigned screen controls. Returning from details reloads enough of the horizontal collection to restore a selected card beyond the first page. All 152 automated tests pass. The large-shelf device check uses a catalog-backed fixture rather than creating artificial watch history in the user's profile.

## Shared sidebar/content geometry

The installed browser uses a shared content group and one layout owner for both sidebar states. Framebuffer captures verify separate sidebar and content regions on initial Home entry and on section, library, search, movie, series, and season views. Repeated expand/collapse transitions and a non-first grid selection retain the selected title. Episode rows wrap within the minimum viewport width, and compact grids retain eight columns. No playback is started; idle protection is verified after cleanup.

The layout contract checks every content control against the sidebar boundary and screen edge in both states, repeated resizing without cumulative drift, intrinsic poster/button sizes, vertical row bounds, and selection preservation during reflow. All 153 tests pass. Device validation uses the 1080p design/output setup; Kodi scales the same layout for other GUI resolutions.

## Eager artwork and repeat navigation

A read-only texture-database check finds four uncached artwork URLs, warms them through the installed add-on's `image://` preloader, and independently confirms all four appear in Kodi's persistent cache (about 0.85 seconds in this sample). A browser wrapper counts actual Session requests: detail Back, reopening the same details, and Home down/up issue no additional catalog reads. Home return takes about 0.3 seconds with polling overhead. The window closes normally and idle protection is verified.

Initial measurements put the full Home metadata response around 0.3 seconds and sampled posters around 70–110 KB. The sampled 400-pixel request selected the same variants as the server default; this is not evidence of an artwork-size speedup. Eager native texture caching, metadata reuse, and batch list updates address separate sources of delay. These observations do not establish a universal frame-rate guarantee or eliminate the first fetch for uncached content.
