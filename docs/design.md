# Minimal Silo Kodi client

Status: implementation proposal, grounded in the Silo v2 contract. The repository contains a development scaffold, not the client described below.

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

Use `/api/v2`, not the retiring v1 bridge. Resolve capabilities from the server instead of matching version strings. The live contract is available at `/api/v2/openapi.json`; record its digest when investigating incompatibility. Keep a handwritten client for the few operations below, rather than generating the whole server API.

Use Python 3.11 and standard-library HTTP/JSON. Kodi's Python APIs are supplied by the target. Start with one plugin entry point and small internal modules for HTTP/authentication, directories, and playback as those responsibilities are implemented. Avoid a general routing framework.

## User experience

Provide a simple, remote-first experience that follows Silo's visual style. The reference is Silo's web UI, adapted for viewing across a room rather than copied at desktop density. Keep reference screenshots and deployment-specific UI examples in ignored `.local-testing/ui-references/`.

The inspected Midnight Cinema theme uses near-black surfaces, restrained borders, light text, white primary actions, and rounded cards. Artwork, title information, and Play/Resume should dominate. Use a conspicuous focus indicator, predictable directional navigation, and readable text at normal TV distance. Restore focus and scroll position after returning from details or playback. Loading and failure states must remain navigable with the remote.

| Presentation approach | Tradeoff |
| --- | --- |
| Standard plugin directories | Smallest implementation, but layout and appearance depend on the installed Kodi skin; insufficient for a consistent Silo interface |
| Add-on-owned XML windows | Own the few Silo screens while retaining Kodi's renderer, input handling, and playback; recommended, subject to an early target prototype |
| Whole-Kodi skin or embedded web UI | Expands ownership beyond this client and introduces unnecessary integration work |

Prototype an add-on-owned poster grid and detail screen through `xbmcgui.WindowXML` before building the complete interface. Verify remote focus, scrolling, responsiveness, and return from playback on CoreELEC. Use this result to settle window lifetime and playback-session ownership together; the earlier plugin-invocation monitor proposal remains provisional.

Limit the first interface to server connection/device sign-in, a profile picker with PIN entry, a library selector and paginated poster grid, title details with Play/Resume and version choice, and season/episode selection. Include profile switching in a consistent location. Keep Kodi's normal playback OSD for pause, seek, audio, and subtitle selection. Continue Watching can follow once server resume is reliable; do not reproduce the web dashboard in the first milestone.

Before release, review licenses and attribution for reused fonts, icons, and artwork, and check Silo's branding guidance. Following the visual language does not require copying the web frontend or distributing reference screenshots.

## Authentication and profile authority

1. Configure a server URL, with no packaged default. Require TLS verification. Validate scheme and origin; do not follow credential-bearing redirects to arbitrary origins.
2. Read `GET /auth/device/capability`; start `POST /auth/device/start` with device name, platform, and `client_purpose: device_login`. This permits later profile switching; a temporary remote-playback handoff binds a single profile and is unsuitable.
3. Display the returned browser verification URL and user code. Poll `/auth/device/poll` at the returned interval, honor `poll_after`, expiry changes and `Retry-After`, and cancel through `/auth/device/cancel` when dismissed. Browser sign-in handles the deployment's OIDC provider; no admin key or stored account password is needed.
4. Save the access/refresh pair under Kodi's add-on profile directory with mode 0600, atomic replacement, and a stable installation device UUID. Never place credentials in plugin navigation URLs, settings exports, or logs. Kodi does not provide an encrypted secret vault here.
5. List `GET /profiles` using account authority. For a PIN profile, call `POST /profiles/{id}/verify-pin` and send the resulting `X-Profile-Token` together with `X-Profile-Id`. Do not persist a PIN. Respect lockout responses without automatic PIN retries.
6. Keep the selected profile distinct from account authentication. Disable Kodi directory disk caching for profile-dependent lists. Include profile identity in navigation context and reject stale entries after a switch; rebuild the library root.

One credential store owns refresh and atomic persistence. Multiple Kodi plugin invocations can overlap: serialize refresh with a local file lock and re-read tokens under that lock. On a refreshable authentication error, refresh and retry once. A transport error or 503 does not log the user out; a refused refresh returns to sign-in. Logout revokes the session when reachable and clears local credentials and profile state. Changing server clears origin-bound state.

For the first release, require playback to stop before switching profiles or signing out. Finish its progress/stop operation under the originating profile before activating another. Never send an old session's progress with a newly selected profile.

## Browsing contract

All paths below are relative to `/api/v2` and use the selected profile's authority. Treat IDs and cursors as opaque strings.

| Screen or action | Endpoint | Behavior |
| --- | --- | --- |
| Libraries | `GET /user/libraries` | Viewer libraries; do not use admin `/libraries` |
| Library | `GET /catalog?source=query&library_id=…&limit=50` | Render returned items and a next-page entry from `page.next_cursor` |
| Movie or series details | `GET /catalog/items/{id}` | Use returned metadata and artwork URLs |
| Seasons | `GET /catalog/series/{id}/seasons` | One folder per returned season |
| Episodes | `GET /catalog/series/{id}/seasons/{num}/episodes` | Playable episodes, respecting unavailable files |
| Versions | `GET /catalog/items/{id}/versions` | Select a playable file; keep item ID and file ID distinct |
| Watch state | `GET /watch/{id}` | Obtain resume and playback detail before starting |

List responses, null values, and file relationships must be checked against real authenticated fixtures before implementing the mapper. Unknown media kinds must not be presented as playable videos. Use `VideoInfoTag` and Kodi list items rather than importing metadata into Kodi's database. Server authorization remains authoritative for every detail and playback request, even if a directory entry was cached by Kodi's UI.

## Playback contract

Read `GET /playback/capabilities`, require protocol 3, and retain the server's `installation_id`. Start through `POST /playback/start` with a fresh `playback_attempt_id`, the selected file and profile, and actual client capabilities. Use `quality_preference: auto`; in the inspected contract, `original` is a deprecated alias, not a guarantee of original bytes. Where `fixed_media_file_v1` is advertised, send `allow_alternate_versions: false` to preserve the chosen version and timeline.

A device capability assertion is a promise, not a wish list. Initially support only validated `original_http` plans. Supply the containers, codec limits, subtitle behavior, and HDR/audio output evidence actually established for this CoreELEC build. Do not describe an unknown output as exact/platform-attested support. Return a clear unsupported-playback explanation when the server cannot produce an acceptable original route. Add remux/transcode only after a user requirement justifies its seek and quality semantics; progressive remux is forward-only in the server contract.

For a playable original plan, use the returned stream URL and required media headers with `xbmcplugin.setResolvedUrl`. Preserve signed URL parameters. Keep account credentials on the API origin; handle server-issued delivery grants according to the plan rather than forwarding bearer credentials indiscriminately to proxies. Verify Kodi forwards the required headers on initial reads and byte-range seeks. Do not require InputStream Adaptive for ordinary HTTP original files.

Kodi should select embedded audio/subtitle tracks from the unchanged container. Verify server-selected track defaults map to Kodi's actual stream indexes. Do not invent index equivalence. External subtitles and persistence of track choices are follow-up work if needed to make the requested media usable.

### Session lifetime

A URL alone is insufficient: Silo requires progress heartbeats, including while paused. The first implementation will keep the playback plugin invocation alive with an `xbmc.Player`/`xbmc.Monitor` loop after resolution. This invocation owns one session, its immutable profile authority, its sequence counter, and its stop identifier. It sends progress every 10 seconds and observes Kodi's actual position and pause state. The target spike must prove the interpreter survives resolution and UI navigation before relying on this ownership model; if it cannot, move this responsibility into one bundled Kodi service, rather than duplicating it across UI callbacks.

V2 progress is `POST /playback/{session_id}/progress` with `installation_id`, monotonically increasing `sequence`, `position`, and `is_paused`. Stop is `DELETE /playback/{session_id}` with `installation_id`, stable `stop_id`, and optional final sequenced position. Retry an uncertain mutation using the same identifiers and body. A later observation gets a later sequence. Use the same start attempt/body when recovering an interrupted start; do not create duplicate sessions on a network timeout.

Playback ends on stop, completion, failure, replacement by another item, or Kodi shutdown. Stop only the session owned by this invocation. A session-not-found response ends reporting; do not recreate it behind the user. On a crash, let server expiry reclaim it rather than adding a durable retry queue. Resume persistence remains server-owned. Explicitly test pause beyond 45 seconds, seeks in both directions, immediate stop, and failure before player readiness.

### HDR, Dolby Vision, and bitrate

Validate the complete player → AVR → display chain. Hardware capability claims alone do not establish the active output, decoder path, or FEL reconstruction. Keep the local device inventory and its measured capabilities in ignored `.local-testing/`.

Preserve the original HEVC bitstream, Dolby Vision metadata and enhancement layer. Do not remux, transcode, or silently accept an HDR10/base-layer fallback as a successful FEL test. Separate decoder evidence, active sink EDID, Kodi settings, and measured output. A Dolby Vision indicator on the TV alone does not prove FEL use; use a known FEL-discriminating clip plus decoder diagnostics and visual confirmation.

Keep bitrate unbounded by arbitrary client defaults, while honoring server policy. Measure the actual media path from the playback device using the authenticated bandwidth-probe capability, and test sustained representative high-bitrate content and seeking. A 1 Gbit/s link, API response latency, and a silent local WAV do not establish sustainable stream throughput. Do not claim a maximum bitrate until measured.

## Delivery sequence and acceptance

1. **UX and lifecycle spike:** confirm visual references and prototype a focused poster grid/detail flow. Validate remote navigation and player return; decide the lifetime owner for Silo heartbeats before expanding the UI.
2. **Account access:** implement device pairing, token persistence/refresh/logout, and profile/PIN selection. Browser approval is the only user credential interaction. Restart retains sign-in; failures do not accidentally change profile authority.
3. **First real playback:** browse enough authenticated catalog data to choose one SDR movie, negotiate original delivery, and play it through Kodi. Prove range seeks, pause beyond 45 seconds, progress heartbeats, stop, and resume observed in Silo. This is the first end-to-end usable milestone.
4. **Complete everyday browsing:** paginate libraries, navigate seasons/episodes, show artwork and details, support versions, and restore navigation state. Verify old profile navigation cannot play under stale authority. Wire these screens to the proven playback path.
5. **Media qualification and recovery:** validate HDR10, DV/FEL, lossless soundtrack passthrough, embedded subtitles, and sustained bitrate; exercise expired tokens, network interruption, immediate stop, and file replacement. Keep hardware-specific results local.
6. **Public release:** verify a clean ZIP install and an upgrade preserving settings and sign-in, then publish a versioned asset through GitHub Releases. State the tested Kodi and API compatibility and playback limitations.

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
