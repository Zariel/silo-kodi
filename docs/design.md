# Minimal Silo Kodi client

Status: authentication, browsing, original-stream playback, quality selection with SDR HLS transitions, and text/embedded PGS subtitle controls are implemented and undergoing device acceptance. Representative combined quality/subtitle and audio-preservation workflows pass. Broader playback qualification, additional subtitle formats, and broader Home error handling remain unfinished. This document describes the complete intended client, grounded in the Silo v2 contract.

## Requirement and boundaries

Provide remote-controlled sign-in, account profile selection, on-demand library browsing, and playback through Kodi on CoreELEC. Preserve source video and audio when Kodi and the active HDMI chain support them. Pause and seek must work without a catalog sync into Kodi.

Silo owns access control, catalog metadata, file selection authorization, and playback sessions. Kodi owns demuxing, decoding, audio passthrough, subtitle rendering, pause, seeking, and HDMI output. The add-on translates between these interfaces. It must not bypass Silo policy by opening an SMB/NFS path or reconstructing an unsigned file URL.

The first usable release covers movies and TV episodes, including their audio tracks and embedded subtitles. Standalone music and audiobooks are out of scope. Publish the add-on as a video provider; audio support means decoding or passing through the soundtrack within a video file.

Exclude catalog synchronization, a local metadata database, whole-Kodi skins, downloads, search/recommendation parity, watch parties, casting, admin operations, automatic adaptation, and server or firmware changes. Do not add a custom player or transcoder.

## Integration choice

| Approach | Fit | Decision |
| --- | --- | --- |
| Existing Jellyfin browsing client through Silo's compatibility listener | Could remove most new client code, but requires checking client behavior, a separate listener, and Silo household profile semantics; root `/System/Info/Public` on the provided URL returned the web app | Keep as an alternative if native playback proves unsuitable; not the initial implementation |
| Small Python add-on using Silo native v2 | Direct device sign-in, explicit account profiles, viewer-scoped catalog, and negotiated source playback | Selected |
| Kodi library sync or direct filesystem access | Duplicates catalog ownership or bypasses Silo playback authority | Does not satisfy this requirement |

Use `/api/v2`, not the retiring v1 bridge. Resolve capabilities from the server instead of matching version strings. The live contract is available at `/api/v2/openapi.json`; record its digest when investigating incompatibility. Keep a handwritten client for the few operations below, rather than generating the whole server API. The [full API audit](api-audit.md) maps all API groups to scope and records action-level contracts and follow-up opportunities.

Use Python 3.11 and standard-library HTTP/JSON. Kodi's Python APIs are supplied by the target. Use one entry module with a script extension for browsing windows and a plugin extension for playback resolution and status reads. Kodi’s RunAddon action prefers the plugin extension, so its root launcher completes the directory request, returns to Kodi Home, and launches the independent UI script. A browsing window must not remain inside directory resolution: returning to an uncached plugin directory can start another browser and obscure the account screen. Keep authentication, catalog reads, and playback in small internal modules. Avoid a general routing framework.

## User experience

Provide a simple, remote-first experience that follows Silo's visual style. The reference is Silo's web UI, adapted for viewing across a room rather than copied at desktop density. Keep reference screenshots and deployment-specific UI examples in ignored `.local-testing/ui-references/`.

Use near-black surfaces, restrained borders, light text, rounded poster cards, and the configured Silo accent for primary actions and active navigation. Artwork, title information, and Play/Resume should dominate. Keep the accent sparse so posters carry most of the color. Use a conspicuous focus indicator, predictable directional navigation, and readable text at normal TV distance. Restore focus and scroll position after returning from details or playback. Loading and failure states must remain navigable with the remote.

Read the accent from `GET /api/v2/theme/branding` (`accent_color`), which the inspected server contract exposes before sign-in. Validate the color before converting it to Kodi color values, and use a neutral light primary action when the accent is absent, invalid, or unavailable. Keep text and the focus outline high-contrast regardless of the chosen accent. Scope cached branding to the server and clear it when the server changes. This does not require copying the web theme system or introducing a separate color preference.

| Presentation approach | Tradeoff |
| --- | --- |
| Standard plugin directories | Smallest implementation, but layout and appearance depend on the installed Kodi skin; insufficient for a consistent Silo interface |
| Add-on-owned XML windows | Own the few Silo screens while retaining Kodi's renderer, input handling, and playback; recommended, subject to an early target prototype |
| Whole-Kodi skin or embedded web UI | Expands ownership beyond this client and introduces unnecessary integration work |

Prototype an add-on-owned poster grid and detail screen through `xbmcgui.WindowXML` before building the complete interface. Verify remote focus, scrolling, responsiveness, and return from playback on CoreELEC. Use this result to settle window lifetime and playback-session ownership together; the earlier plugin-invocation monitor proposal remains provisional.

Limit the first interface to server connection/device sign-in, a profile picker with PIN entry, a library selector and paginated poster grid, title details with Play/Resume and version choice, and season/episode selection. Include profile switching in a consistent location. Keep Kodi's normal playback OSD for pause, seek, audio, and subtitle selection. Continue Watching can follow once server resume is reliable; do not reproduce the web dashboard in the first milestone.

### Initial TV layouts

- **Browse:** a narrow left navigation rail with library names and profile access, followed by a spacious poster grid. Begin with approximately six posters across the content area at 1080p and adjust after viewing on a TV. Show the title and secondary metadata below each poster. Keep badges legible and limited to useful source-format information; they describe the file, not verified output capability.
- **Details:** a full-width backdrop fading into the dark surface, with a poster, title or title artwork, a short metadata row, synopsis, and prominent Play/Resume action using the configured accent. Put version, audio, and subtitle choices nearby when implemented. Keep raw paths and technical diagnostics out of the normal viewing flow.
- **Series:** reuse the backdrop/poster detail layout, showing series metadata and a row of season posters with season labels and episode counts. The main action must name its actual target, such as Resume or Play episode 1; derive it from server watch state rather than always starting over.
- **Season:** retain the series backdrop, show the season poster and breadcrumb, and present episodes as landscape stills with episode number, title, runtime, and a short synopsis. Use larger cards and less text than a desktop grid, and preserve the selected season/episode on Back. Do not make series or season containers playable as if they were files.
- **Remote focus:** combine a high-contrast outline with a modest card emphasis, without moving neighboring cards. Left from the first column enters navigation; Right returns to the remembered content item. Back returns to the previous screen and restores its selection. Set initial detail-page focus to Play/Resume. Avoid hover-only actions.
- **Scope:** reproduce this visual language with a small set of screens. Recommendations, ratings, favorites, trailers, and administration are not prerequisites for the first usable client. Use placeholder artwork gracefully when a poster is unavailable.

Before release, review licenses and attribution for reused fonts, icons, and artwork, and check Silo's branding guidance. Following the visual language does not require copying the web frontend or distributing reference screenshots.

## Authentication and profile authority

1. Enter a server URL manually, with no packaged default or network discovery. Require TLS verification. Validate scheme and origin; do not follow credential-bearing redirects to arbitrary origins.
2. Read `GET /auth/device/capability`; start `POST /auth/device/start` with device name, platform, and `client_purpose: device_login`. This permits later profile switching; a temporary remote-playback handoff binds a single profile and is unsuitable.
3. Encode the returned `verification_uri_complete` as a QR code using an established QR library, and also display the browser verification URL and user code as a fallback. Sign-in and approval happen in Silo; do not implement a username/password form in the add-on. Poll `/auth/device/poll` at the returned interval, honor `poll_after`, expiry changes and `Retry-After`, and cancel through `/auth/device/cancel` when dismissed. Browser sign-in handles the deployment's OIDC provider; no admin key or stored account password is needed.
4. Save the access/refresh pair under Kodi's add-on profile directory with mode 0600, atomic replacement, and a stable installation device UUID. Never place credentials in plugin navigation URLs, settings exports, or logs. Kodi does not provide an encrypted secret vault here.
5. List `GET /profiles` using account authority. For a PIN profile, call `POST /profiles/{id}/verify-pin` and send the resulting `X-Profile-Token` together with `X-Profile-Id`. Do not persist a PIN. Respect lockout responses without automatic PIN retries.
6. Keep the selected profile distinct from account authentication. Disable Kodi directory disk caching for profile-dependent lists. Include profile identity in navigation context and reject stale entries after a switch; rebuild the library root.

One credential store owns refresh and atomic persistence. Multiple Kodi plugin invocations can overlap: serialize refresh with a local file lock and re-read tokens under that lock. On a refreshable authentication error, refresh and retry once. A transport error or 503 does not log the user out; a refused refresh returns to sign-in. Logout revokes the session when reachable and clears local credentials and profile state. Changing server clears origin-bound state.

For the first release, require playback to stop before switching profiles or signing out. Finish its progress/stop operation under the originating profile before activating another. Never send an old session's progress with a newly selected profile.

## Browsing contract

All paths below are relative to `/api/v2` and use the selected profile's authority. Treat IDs and cursors as opaque strings.

| Screen or action | Endpoint | Behavior |
| --- | --- | --- |
| Libraries | `GET /user/libraries` and `/settings/values/effective?keys=ui.disabled_library_ids` | Filter self-hidden viewer libraries; do not use admin `/libraries` |
| Library | `GET /catalog?source=query&library_id=…&limit=50` | Use `skip_total=true`; render items and a next-page entry from `page.next_cursor` |
| Movie or series details | `GET /catalog/items/{id}` | Use returned metadata and artwork URLs |
| Seasons | `GET /catalog/series/{id}/seasons` | One folder per returned season |
| Episodes | `GET /catalog/series/{id}/seasons/{num}/episodes` | Playable episodes, respecting unavailable files |
| Versions and resume menu | `GET /watch/{id}` | Use its playable versions and profile progress together; keep item ID and file ID distinct |
| Playback track metadata | `GET /catalog/items/{id}/versions` | The independent playback owner reads trusted track inventory under its originating profile |

List responses, null values, and file relationships must be checked against real authenticated fixtures before implementing the mapper. Unknown media kinds must not be presented as playable videos. Use `VideoInfoTag` and Kodi list items rather than importing metadata into Kodi's database. Server authorization remains authoritative for every detail and playback request, even if a directory entry was cached by Kodi's UI.

## Playback contract

Read `GET /playback/capabilities`, require protocol 3, and retain the server's `installation_id`. Start through `POST /playback/start` with a fresh `playback_attempt_id`, the selected file and profile, and actual client capabilities. Use `quality_preference: auto`; in the inspected contract, `original` is a deprecated alias, not a guarantee of original bytes. Where `fixed_media_file_v1` is advertised, send `allow_alternate_versions: false` to preserve the chosen version and timeline. Independently require every playable start or replan to name the chosen `effective_media_file_id` before exposing its media grant. Track inventory and resume positions belong to that file, even when a server does not advertise fixed-file negotiation. Retain the session identity for cleanup if the returned plan is rejected.

A device capability assertion is a promise, not a wish list. The client declares codec families and a 2160p ceiling, and delegates original-file presentation through Silo's `client_managed_dynamic_range_v1` claim. Kodi selects its decoder, renderer, and HDMI/audio behavior from the original bytes. This is not an assertion that every Kodi installation supports native HDR, Dolby Vision, FEL, or audio passthrough. Keep decode evidence `declared`, do not populate unverified sink-format or passthrough claims, and report tested output combinations separately. The claim applies only to `original_http`; HLS retains its SDR H.264/AAC declaration. Progressive remux remains unsupported because it is forward-only.

This ownership model avoids reconstructing a decoder/display matrix from incomplete Kodi APIs. Display capability labels and configured passthrough flags cannot establish native decoding or active HDMI output. A user-selected device profile would add state that can become stale after firmware or connection changes. The native executor already makes these choices at playback time; use its observed runtime state and independent output evidence for qualification instead of adding a second selection policy.

For a playable original plan, pin the returned stream URL and required media headers in the attempt's loopback relay, then pass its local URL to `xbmcplugin.setResolvedUrl`. Preserve signed URL parameters and attach current account and profile authority on every upstream request. Keep account credentials on the API origin; cross-origin delivery remains unsupported. The relay forwards original bytes and range metadata, while Kodi owns decoding and seeking. Do not require InputStream Adaptive for ordinary HTTP original files.

Kodi should select embedded audio/subtitle tracks from the unchanged container once server track identities can be mapped to Kodi's actual stream indexes. Do not invent index equivalence. The implemented subtitle path accepts server-selected SRT or WebVTT sidecars for original media, attaches current profile authority, and applies the sidecar after startup seeking settles. Both use the source clock; nonzero artifact timing origins are rejected until timeline mapping is implemented. An Off decision hides subtitles. The browser offers Now playing → Subtitles for supported sidecars, embedded PGS, and Off. Original MKV PGS playback negotiates native embedded support and maps the server’s global stream index to a unique Kodi subtitle using metadata, never ordinal arithmetic. The owner observes the requested native selection and visibility before completing the transition. Supported transcoded HLS can instead carry server-burned captions; Kodi subtitle rendering stays disabled for that decision. Authored ASS/fonts, additional bitmap formats, and persistence of track choices remain to be implemented and qualified.

### Subtitle controls

Quality uses the same revision-bound control channel. The owner negotiates a server-provided label, opens a distinct relay URL with a fresh Kodi ListItem, and restores position and pause before publishing the new selection. See the [quality playback design](quality-playback.md) for delivery limits and acceptance evidence.

The playback owner publishes only subtitle labels, opaque track identities, selection, and a revision in Kodi Home-window properties. The browser uses a native selection dialog and submits a choice against that revision. The owner rejects stale requests and retains sole ownership of Silo mutations, observed position, and the relay. Cleanup removes both metadata and pending requests. No credentials or media URLs cross this UI channel.

A track choice uses the active plan's inventory and a `track_change` replan. Off omits the subtitle identity; unchanged audio identity is preserved. Use a stable request ID and body for retries. Verify that the returned plan still uses the same media file before updating relay grants and applying the subtitle decision through Kodi. Original-to-original subtitle changes keep the player open. A replan involving transcoded HLS reopens the video and restores position and pause: Kodi's existing demuxer can retain segment references retired by the new plan. Recheck ownership after the network operation so a replacement video cannot receive the old session's subtitle.

Selections made directly in Kodi’s subtitle OSD are not yet reconciled into subsequent Silo replans. Native Kodi subtitle selection cannot populate Silo-only artifacts or express Silo's track-change contract by itself. Giving the browsing window its own session would duplicate playback ownership. A separate permanent service is unnecessary while the existing invocation owns playback reliably. Keep this small UI channel scoped to that invocation; it is not a durable command queue.

### Session lifetime

A URL alone is insufficient: Silo requires progress heartbeats, including while paused. A separate playback plugin invocation stays alive with an `xbmc.Player`/`xbmc.Monitor` loop after resolution; the browsing window does not own it. This invocation owns one session, its profile authority, its sequence counter, and its stop identifier. It sends progress every 10 seconds and observes Kodi's actual position and pause state. A process lock prevents another playback owner or account/profile/server mutation until final stop completes. Target checks confirm playback beyond 60 seconds, persisted progress, recovery from a missing-file start, and external replacement without stopping the new video. Synthetic overdue client deadlines trigger real renewal during original and HLS playback without losing pause, identity, or seeking. Broader network-interruption qualification remains open. If invocation lifetime proves unreliable, move this responsibility into one bundled Kodi service rather than duplicating it across UI callbacks.

Media requests need current account and profile headers even when the plan supplies a signed stream reference. `stream.headers` deliberately omits the account bearer. Negotiate `header_authenticated_media_v1` when advertised. The relay obtains fresh authority from the shared session store for each GET or HEAD without reopening Kodi. Its resource paths are fixed by the plan, scoped to this attempt, and accessible only over loopback. Stop active transfers and join workers before closing the Silo session and releasing playback authority.

The [media transport design](media-transport.md) records the alternatives, implementation contract, and acceptance evidence. Real credential rotation, long pause, seeking, subtitles, and external replacement pass through the integrated relay. A ten-minute high-bitrate original playback window passes sampled clock and buffering checks; the [compatibility matrix](playback-references.md) records measurement limits. Synthetic client-expiry acceptance qualifies renewal; natural wall-clock expiry is optional additional coverage. Broader bitrate peaks and render-quality qualification remain pending.

For resume, use the plan's player position. Do not report startup position zero while Kodi is still seeking to the saved point. The target did not honor `StartOffset` reliably; the playback owner explicitly seeks after A/V readiness and waits for the observed position before reporting progress.

V2 progress is `POST /playback/{session_id}/progress` with `installation_id`, monotonically increasing `sequence`, `position`, and `is_paused`. Stop is `DELETE /playback/{session_id}` with `installation_id`, stable `stop_id`, and optional final sequenced position. Retry an uncertain mutation using the same identifiers and body. A later observation gets a later sequence. Use the same start attempt/body when recovering an interrupted start; do not create duplicate sessions on a network timeout.

Playback ends on stop, completion, failure, replacement by another item, or Kodi shutdown. Stop only the session owned by this invocation. A session-not-found response ends reporting; do not recreate it behind the user. On a crash, let server expiry reclaim it rather than adding a durable retry queue. Resume persistence remains server-owned. Explicitly test pause beyond 45 seconds, seeks in both directions, immediate stop, and failure before player readiness.

### HDR, Dolby Vision, and bitrate

Validate the complete player → AVR → display chain. Hardware capability claims alone do not establish the active output, decoder path, or FEL reconstruction. Keep the local device inventory and its measured capabilities in ignored `.local-testing/`.

Preserve the original HEVC bitstream, Dolby Vision metadata and enhancement layer. Do not remux, transcode, or silently accept an HDR10/base-layer fallback as a successful FEL test. Separate decoder evidence, active sink EDID, Kodi settings, and measured output. A Dolby Vision indicator on the TV alone does not prove FEL use; use a known FEL-discriminating clip plus decoder diagnostics and visual confirmation.

Keep bitrate unbounded by arbitrary client defaults, while honoring server policy. Measure the actual media path from the playback device using the authenticated bandwidth-probe capability, and test sustained representative high-bitrate content and seeking. A 1 Gbit/s link, API response latency, and a silent local WAV do not establish sustainable stream throughput. Do not claim a maximum bitrate until measured.

## Delivery sequence and acceptance

Deliver these six milestones in order. Each milestone must have a reproducible local acceptance check and small logical commits. UI work starts with the login screen and grows with browsing; a separate full browsing prototype is not a prerequisite for authentication.

### 1. Authentication

- Manual server URL entry; no network discovery or automatic server selection.
- QR-based Silo device pairing, with a readable URL and user code fallback. The person signs in and approves through Silo's browser UI; the add-on never collects the account password.
- Pending, approved, denied, canceled, expired, and network-error states. Respect polling intervals and rate limits. Allow a fresh attempt after expiry.
- Persist and refresh login credentials, sign out, and handle revoked sessions without refresh loops. Select an account profile and verify its PIN when needed. Clear origin-bound state on a server change.
- Read server branding without blocking authentication if it is unavailable.
- **Acceptance:** approve a real pairing, select a profile, restart Kodi and remain signed in, then sign out. Exercise canceled/expired pairing and invalid profile PIN without changing the selected authority.

#### Local authentication testing

Provide a developer harness mode that runs the same pairing flow on the target and makes the QR image and verification link accessible from the workstation, so approval does not require a powered TV. The user still approves through Silo. Keep pairing artifacts, server/target configuration, and diagnostics in ignored `.local-testing/`; leave tokens in protected local credential storage, never the ZIP or tracked fixtures. Do not add a production authentication bypass or require an admin API key.

Keep live integration checks separate from deterministic tests using synthetic responses. The latter cover expiry, cancellation, failed refresh, and polling delays without repeatedly consuming real sign-in requests. Exercise production UI separately on Kodi; a successful headless flow alone does not prove remote navigation or QR legibility. Normal development redeployment must preserve sign-in; any reset must be explicit and limited to the test state.

### 2. Media browsing and screens

- Render viewer libraries, paginated movie/series grids, title details, season posters, and episode cards following the visual direction above.
- Provide clear loading, empty, access-denied, and retry states. Keep remote navigation responsive and restore focus/scroll position when returning.
- Support profile switching, rebuilding profile-dependent screens and rejecting stale navigation. Load artwork without creating a local catalog mirror.
- **Acceptance:** browse multiple pages and seasons using only the remote, open details, go Back, and switch profiles without leaking the previous profile's catalog. Include missing artwork and an unavailable server.

### 3. Basic media playback

- Resolve a selected movie or episode through Silo's playback negotiation and hand an original HTTP plan to Kodi. Keep this milestone focused on representative SDR media with its soundtrack.
- Establish the session owner now: start/retry identity, progress heartbeats, current pause state, stop/completion/error cleanup, and immutable profile context. These are required protocol behavior, not optional polish for milestone 4.
- Keep native Kodi controls available. Do not build a custom playback OSD or intentionally disable controls that Kodi already supplies. Explicit UX and full behavior validation follow in milestone 4.
- Fail clearly on an unsupported delivery plan instead of silently degrading or bypassing Silo authorization.
- **Acceptance:** select a real movie and an episode from the UI, play beyond the session-idle window, stop or finish, return to the correct screen, and verify Silo records and closes the correct session. Exercise a failed start and replacement by another item.

### 4. Full playback behavior and media qualification

- Validate pause/resume, a long pause, forward/backward seeks, and recovery after ordinary interruptions.
- Offer Resume and Play from beginning using server watch state and protocol start positions. Silo's inspected protocol documents saved resume as the default and explicit `start_position: 0` as start over; verify these semantics through an independent Silo client. Do not maintain a separate resume database.
- Validate HDR10, Dolby Vision including FEL reconstruction, DTS-HD MA, TrueHD/Atmos, audio track switching, and representative sustained high bitrates. Separate source-format labels from observed HDMI output, and keep device-specific evidence local.
- **Acceptance:** the selected resume/restart action yields the expected player position; stop and reopen retain Silo's progress; another profile has independent progress. Confirm actual display/AVR output and decode behavior for each claimed format.

### 5. Playback quality and subtitles

The [quality playback design](quality-playback.md) records the native HLS target probe, server and mobile-client contracts, transport alternatives, and remaining transition checks.

- Discover server-provided quality choices and offer a small quality selector. Keep source-version selection distinct from quality adaptation.
- Implement supported delivery/replan paths needed for those choices, preserving position and session semantics. Do not assume progressive remux offers arbitrary seeking or that quality adaptation preserves Dolby Vision/FEL.
- Add explicit subtitle choices, Off, language/forced/default behavior, and external subtitle delivery where supported. Embedded tracks Kodi already exposes may work earlier; this milestone owns the complete selection behavior. Validate text and bitmap subtitles and any server-required burn-in path before claiming them.
- **Acceptance:** change quality and subtitles on representative files, verify the actual resulting stream and position, and handle unavailable choices without a silent downgrade or playback loop.

### 6. Silo Home as the main page

Implementation status: profile-bound layout, section-card, and paginated section reads are implemented. The deployed server returns its layout and cards through these methods; an expanded section returns an opaque next-page cursor. Home is the entry screen with two visible horizontal rows loaded on demand, empty rows omitted, expanded section browsing, and content-ID-based return focus. Device checks pass entry, episode details, return focus, row scrolling, expanded sections, and library navigation. A temporary PIN-protected profile passes incorrect-PIN rejection, correct selection, isolated Home rows, and switching back to the original profile. The same open Home window also refreshes Continue Watching after an episode is played and stopped; an independent server read confirms the saved position and card identity. Aggregate-only and profile-settings fallback paths pass device checks with injected endpoint unavailability. Profile settings supply visible section identities and ordering; when positions are absent, the client applies the default recipe order to those discovered identities. Broader error cases remain to qualify. No optional layout parameters are sent, so the basic read does not require capability negotiation.

- Open Home after sign-in and profile selection. Keep libraries and profile switching accessible from the main navigation. Follow the Silo TV references and server-configured accent, reusing existing cards, details, and playback actions.
- Fetch the acting profile's section layout from `GET /api/v2/home/layout` and load cards through `/api/v2/home/sections/{id}/items`. Preserve server ordering and visibility, including supported custom sections. Use `/api/v2/home/capabilities` to negotiate optional features such as including the first rows' cards with the layout.
- If the layout endpoint is unsupported, use `/api/v2/home/sections` where available. If both endpoints are unsupported, discover rows through `/profile/sections/settings?scope=home`, omit hidden rows, and use their positions. If positions are absent, order the discovered rows by Silo’s default recipes, leaving unfamiliar recipes in stable order afterward. Never guess `default-*` section IDs: those are seed templates, while configured rows have generated identities. If no discovery endpoint is supported, report Home as unavailable and keep libraries accessible. Fetch content from supported server APIs; do not create a local catalog, recommendation engine, or watch-state store. Authentication failures and temporary network errors must remain explicit errors, not trigger a compatibility fallback.
- Load rows on demand, handle empty and unsupported sections, and preserve remote focus when returning from details or playback. Refresh server-owned progress after playback and discard the previous profile's Home state on profile changes. Home editing and section reordering are outside this milestone.
- Use `/home/sections/{id}/items` for a bounded row and `/catalog?source=section&scope=home&section_id=…` for expanded section browsing with opaque cursors. Omit `sort` to preserve the recipe's order and omit `type=video`, which would exclude episode cards. Filter unsupported media types locally without discarding the server cursor.
- **Acceptance:** Home is the entry screen; supported rows follow the profile's server layout; selecting a card reaches the correct details and playback flow. Verify remote navigation, row pagination where supported, return focus, updated Continue Watching, empty/error states, profile isolation, and the aggregate-endpoint compatibility fallback.

### Cross-cutting work and future work

Add focused tests and target smoke checks alongside each milestone. Keep packaging usable throughout, and validate clean install, upgrade preserving credentials, and sanitized diagnostics before a public release. GitHub prereleases may deliver completed milestones; release automation is not a prerequisite for local iteration.

Use the Silo Apple and Android clients as references for API flows, playback semantics, and user expectations. The server contract remains authoritative, and Kodi owns platform decoding/output. Do not infer Kodi codec support from a mobile client's capability declaration or copy its entire feature set.

When a requested behavior is absent from the deployed Silo API, stop at a clear unsupported state and record future work with the missing contract, evidence, and an existing upstream issue link if one can be verified. Search upstream issues when the gap is established; do not invent an issue or open one automatically. Do not add a parallel local implementation of server-owned progress or state. Resume is documented upstream and is therefore a validation task, not an assumed missing feature.

## Development and distribution

Use the existing package/deploy workflow for local iteration: build the installable ZIP, transfer it over SSH, replace the add-on tree, and ask Kodi to rescan. Keep local endpoints and SSH configuration in ignored `.local-testing/`. Expand the package allowlist as XML windows, resources, and modules are added. Keep the same package builder for development and release artifacts.

For GitHub Releases, add CI for syntax/manifest checks, focused contract tests, and packaging. A version tag should match `addon.xml`; a tag workflow builds `plugin.video.silo-<version>.zip` and a SHA-256 checksum, then attaches those artifacts and release notes to the release. The automatically generated repository source archive is not the installable add-on package. Begin with prereleases until real-device acceptance passes.

The first distribution method is Kodi's **Install from zip file**, with manual upgrades. A Kodi repository for automatic updates is a later feature; GitHub Releases alone does not provide Kodi's update feed. Do not add an updater inside the client. No publishing or release credentials are needed to develop locally.

Focused tests should distinguish these plausible failures: paging stops at 50 items; item IDs are mistaken for file IDs; a failed PIN changes active authority; stale profile entries still play; refresh races discard rotated tokens; a delayed progress report overwrites a newer seek; stop races the next session; playback is advertised before the demuxer is ready; remux loses FEL; a redirect leaks API credentials. Test public behavior and independent observations, not call order alone.

## Sources and contract baseline

- Upstream inspected at [`489fe4d55735f3855b2a0d6276e57d148891b456`](https://github.com/Silo-Server/silo-server/tree/489fe4d55735f3855b2a0d6276e57d148891b456); this is a research reference, not a required server revision. Record deployment-specific versions and API contract digests in ignored `.local-testing/`.
- [Authentication](https://github.com/Silo-Server/silo-server/blob/489fe4d55735f3855b2a0d6276e57d148891b456/docs/auth-api.md), [v2 playback](https://github.com/Silo-Server/silo-server/blob/489fe4d55735f3855b2a0d6276e57d148891b456/docs/playback-api.md), and [protocol 3](https://github.com/Silo-Server/silo-server/blob/489fe4d55735f3855b2a0d6276e57d148891b456/docs/architecture/playback-protocol-v3.md).
- [Native API lifecycle](https://github.com/Silo-Server/silo-server/blob/489fe4d55735f3855b2a0d6276e57d148891b456/docs/architecture/api-contract.md) and [Jellyfin compatibility boundaries](https://github.com/Silo-Server/silo-server/blob/489fe4d55735f3855b2a0d6276e57d148891b456/docs/jellycompat-api.md).
- [Kodi add-on structure](https://kodi.wiki/view/Add-on_structure); use the target's `JSONRPC.Introspect` for its RPC contract.

- [Silo public UI showcase](https://siloserver.org/) and [Midnight Cinema theme](https://github.com/Silo-Server/silo-server/blob/489fe4d55735f3855b2a0d6276e57d148891b456/web/src/app.css).
- [Kodi XML windows](https://xbmc.github.io/docs.kodi.tv/master/kodi-base/dd/d4d/group__python__xbmcgui__window__xml.html) and [GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).

- Reference clients: [Silo Apple](https://github.com/Silo-Server/silo-apple) and [Silo Android](https://github.com/Silo-Server/silo-android).
