# Select playback quality without losing position

Status: quality controls, replans, and native player transitions are implemented. The installed add-on passes original → 360p → Auto → 360p through the remote menu, including paused changes and subsequent resume. Capabilities advertise original HTTP and SDR H.264/AAC HLS. Combined text-subtitle/quality transitions pass representative checks. A selected nondefault AC3 soundtrack survives original → 360p → Auto on a multi-audio fixture. Broader track metadata, interruption cases, and media qualification remain unfinished.

## Requirement and ownership

Offer the current plan's server-supported qualities and Auto. Preserve the observed source position, pause state, profile authority, and session lifecycle when changing quality. Do not infer a successful transition from the replan response alone: Kodi must open the resulting delivery and reach the requested position.

Silo owns the quality ladder, encoding, and plan. Kodi owns HLS demuxing, decoding, buffering, and playback. The existing playback invocation owns the transition and its relay. The browser submits a revision-bound choice through the same channel as subtitles; it does not start another session or operate the player independently.

## Protocol findings

- `available_qualities` contains the selectable entries. Add Auto locally, preserve server order, and send the selected entry's `label` unchanged as `quality_preference` with `operation: quality_change`. Do not recreate the ladder from resolution or bitrate.
- `active_quality`, when advertised, describes the delivered rung. Keep Auto selected when the session preference is Auto, regardless of the delivered rung.
- Lower transcode entries require HLS eligibility and server/account policy. The class is `hls`, and its container declaration is also `hls`; segment container names do not replace this delivery-container value.
- Original HTTP and transcoded HLS use a complete timeline: source offset zero and local seeking to `player_start_seconds`. Copy-remux HLS has a different, incomplete timeline and requires server reanchoring. Do not enable remux HLS merely because transcoded HLS works.
- A successful replan can commit a new server plan before the player opens it. Retain the newest server identity even if local playback fails; an old rendered plan is not authority to replan from a superseded ID.
- With `header_authenticated_media_v1`, the inspected transcode playlist and its segments are served through the authenticated API origin. A fixed bearer handed to Kodi still needs renewal for later requests.

## Delivery alternatives

| Approach | Assessment |
| --- | --- |
| Kodi native HLS with fixed URL headers | Target start and seek pass; does not satisfy credential renewal for later segment requests |
| InputStream Adaptive | Adds a binary dependency and another configuration contract; the native player already handles the tested stream. Revisit only for a demonstrated missing capability |
| Native Kodi HLS through the attempt relay | Preserves Kodi's media ownership and per-request authority. Requires bounded playlist rewriting and scoped segment resources |
| Add-on HLS downloading, buffering, or decoding | Duplicates player responsibilities and is unnecessary for the observed stream |

Extend the attempt relay for the server's observed HLS shape, retaining native Kodi playback. The first qualified path should be SDR H.264/AAC transcoded HLS with a complete source timeline. This is an implementation stage, not a reduction of the final HDR, lossless audio, or quality requirements.

## Relay extension

The observed media playlist is a finite VOD playlist with relative segment references. Fetch it with current profile authority, enforce a size limit, and resolve references against the validated upstream playlist URL. Replace references with opaque loopback resources. Validate every resolved origin before exposing it. Retain upstream queries and required headers without exposing bearer credentials to Kodi.

The implemented relay accepts complete UTF-8 media playlists with MPEG-TS segment references, up to 1 MiB and 10,000 references. It rejects unknown HLS tags, nested playlists, encryption keys, initialization maps, cross-origin references, and truncated bodies. GET and HEAD describe the rewritten representation. Resource replacement retires the old generation, and a delayed playlist response cannot publish references into the new generation. These bounds cover the observed server transcode shape; other shapes need explicit implementation and qualification.

Playlist rewriting must update content length and avoid forwarding validators for the unmodified representation. A HEAD response must describe the representation actually served. Bound resource growth and reject unsupported reference-bearing tags instead of letting Kodi bypass the relay. If an HLS variant, initialization segment, encryption key, or subtitle rendition is encountered, explicitly support its reference contract or reject that plan; do not silently ignore it.

Keep resource publication scoped to the current plan generation. A late response from an old playlist must not reinstall retired segment grants after a quality change. Existing transfers retain their opened resource and remain cancellable by session cleanup. The relay does not parse media segments or choose quality.

## Player transition

Capture Kodi's actual position and pause state before requesting a quality change. Keep the current profile and track identities. Serialize the replan with other control mutations, preserve its request identity on uncertain retries, and validate the returned delivery, timeline, source, and subtitle decision before applying it.

Reopening Kodi is necessary when changing from an original file to HLS or back. Treat this as a transition inside the existing session owner. Old stop/end callbacks must not close the new delivery. Recheck actual player identity before applying position, subtitles, pause, progress, or cleanup. A video opened by another caller belongs to that caller.

Kodi broadcasts player callbacks to all registered Python Player instances, and their signatures omit the file identity. Give each intended delivery transition a distinct local video URL and compare the observed current file against that expected URL. The same-core VideoPlayer reopen path emits Started and AVStarted without an intervening Stopped/Ended pair; a core replacement can emit Stopped. Do not require one fixed callback sequence. Keep a bounded pending transition until the expected URL reaches A/V readiness, and preserve the original plugin route on a fresh ListItem for bookkeeping. Reusing Kodi's current item can retain the old dynamic path even after its ordinary path changes.

After readiness, restore the plan's player position, wait for the observed clock to settle, apply the subtitle decision, and restore pause. Do not report startup zero as a new watch position. Only publish the completed UI selection after the player reaches the intended state. If the committed plan cannot be opened, report the failure and clean up the owned session rather than continuing with stale server identity.

Apply this transition to every replan involving transcoded HLS, including subtitle-only changes. The target retained old segment URLs after a subtitle replan; a subsequent seek received 404 for a retired grant. Reopening creates a new demuxer that consumes the new playlist. Keep grant retirement in the relay instead of extending old-plan authority to accommodate a cached playlist. Original-to-original sidecar changes can keep the player open.

## Preserve the selected soundtrack

The installed-player regression selects a nondefault AC3 soundtrack, pauses, changes to 360p, then returns to Auto. It verifies the returned original still selects AC3, with position and pause preserved. Copying the previous plan's `selected_tracks` alone does not capture a choice made through Kodi's audio controls. Kodi can also retain a native choice across playback starts, independently of the server's initial selection.

Keep reconciliation in the playback owner. Before a quality or subtitle replan, observe the current native audio selection and map it to the source inventory. Submit that identity with the same replan rather than starting a second session or performing a separate track-change mutation. After reopening an original file, select the corresponding native stream and observe it selected before publishing a completed transition. For packaged HLS, retain the plan's source identity; its single delivered audio stream does not have the source's index.

The required source inventory is available from the catalog item's versions response, not the playback plan. Carry the content ID from browsing into the playback route, fetch the matching file's inventory under the playback profile, and keep it scoped to that invocation. Do not persist a second catalog or infer content identity from a file name.

Kodi's JSON-RPC audio index is an ordinal in the current player's audio list. Silo's index is an ordinal in the probed source audio inventory. These often align for ordinary original files, but Kodi can select one program from a multi-program container while Silo probes all streams. Do not use index equality as identity. Match source metadata against observed native streams, accepting only an unambiguous correspondence:

- Account for Kodi's DTS codec names, such as `dtshd_ma` and `dca`, versus ffprobe's `dts`.
- Normalize recognized language codes with Kodi's language conversion. Unknown values must not become equal solely because conversion returns an empty string.
- Compare channel count and available title/profile evidence. Kodi decorates embedded titles with a stream-type suffix; repeated or absent titles are not unique identities.
- Treat default flags as metadata, not evidence that the default stream is currently selected. Reject unresolved matches before a replan, leave the current playback running, and explain why the requested transition is unavailable.

Silo's `client_selected_audio_track_v1` claim on `original_http` permits a nondefault source soundtrack without requiring a remux. The add-on advertises it when it has fetched the selected file's audio inventory and applies and verifies the server selection on original playback. A server probe carried the nondefault source identity through 360p HLS and back to original with this claim; the installed-player regression separately verifies native restoration. Do not add the claim to HLS or apply a source ordinal to its packaged audio list.

Missing inventory or ambiguous metadata prevents preserving native audio across a replan. A rejected request before mutation leaves playback running. If an accepted original plan's audio identity cannot be mapped or selected, fail and clean up the session rather than playing a different soundtrack. File-only developer routes can still start playback but need the catalog content ID for original audio reconciliation.

Acceptance must include original → HLS → original with a nondefault soundtrack, a paused transition, subtitle replans, a reordered native inventory, ambiguous metadata, and replacement playback during selection. Independently observe the final selected native stream and preserved position; a successful server response alone does not prove restoration.

## Evidence and remaining acceptance

A target API probe advertised experimental HLS support without changing installed capabilities. The server returned six fixed rungs for the selected SDR fixture. Selecting its 360p entry returned `server_transcode_hls`, a full timeline, and a finite authenticated media playlist. A separate temporary script opened a fresh 360p plan in Kodi's native player, sought to 90 seconds, observed clock advancement, then stopped and closed the session. No InputStream Adaptive configuration or device output settings changed.

That initial probe established native-engine feasibility only; subsequent checks below cover integration separately.

A subsequent target probe used the relay for the playlist and segments, paused, rotated the real access credential, sought to nine minutes, and observed advancing playback and media requests with fresh authority. Controlled-origin tests independently reject stale authority and verify query preservation, rewritten HEAD length, retired references, and late responses after a replan. Natural expiry remains unqualified.

The shared replan implementation has also been exercised against the server: original to 360p at 120 seconds, subtitle Off retaining 360p, and Auto returning to original at 125 seconds. The returned plans preserved the requested start positions, and the probe closed its session. This checks the negotiation contract without opening Kodi playback; it does not qualify player transitions. Focused tests cover unknown labels, stable retries, track preservation, quality persistence across subtitle changes, and rejection of an anchored HLS timeline while retaining the committed plan for cleanup.

The probe also established a source-identity requirement. On every ListItem used to reopen playback, preserve the genuine originating plugin route in `original_listitem_url`. Kodi otherwise treats the temporary relay URL as a file when persisting watched state, a bookmark, and stream details. Each path can query the file modification date, producing three HTTP HEAD requests during shutdown. Plugin identities skip those modification-date lookups. The target's native stop completed in 0.28 seconds with the property preserved; relay and session cleanup then completed normally. Normal plugin resolution supplies this property, but a direct `Player.play` reopen must retain it explicitly.

The installed add-on's remote-menu acceptance selected 360p and independently observed Kodi's decoded height and preserved position. Returning to Auto restored the source resolution while paused. Selecting 360p again preserved pause and position, and resuming advanced the clock. Cleanup released playback authority and restored the screensaver. A subsequent visual check confirmed the same WebVTT cue in original, 360p HLS, and returned Auto playback, and its absence with Off in HLS. Additional soundtrack metadata, interruption during reopen, and all offered rungs remain unqualified.

The full acceptance scope remains:

1. Playlist/segment origin validation, query preservation, bounded parsing, unsupported references, stale generations, truncation, cancellation, and current authority through the loopback interface.
2. Real original → lower quality → Auto transitions, including repeated choices, seeking in both directions, and independently observed Silo progress.
3. A quality change while paused, delayed readiness, an unavailable rung, an uncertain replan response, stop during transition, and external replacement during transition.
4. Selected text subtitles and audio behavior across transitions. Do not equate track numbers across original and packaged media.
5. Credential rotation during HLS and a later segment request, followed by natural-expiry qualification.

## References

- [Silo quality and timeline contract](https://github.com/Silo-Server/silo-server/blob/489fe4d55735f3855b2a0d6276e57d148891b456/docs/architecture/playback-protocol-v3.md).
- [Android server-owned quality menu](https://github.com/Silo-Server/silo-android/blob/0545b85deb3be6c32868200a7b2b3edbd3ab02ef/shared/src/commonMain/kotlin/org/siloserver/silo/model/playback/PlaybackQualityMenu.kt).
- [Android replan and server-plan ownership](https://github.com/Silo-Server/silo-android/blob/0545b85deb3be6c32868200a7b2b3edbd3ab02ef/android-shared/src/androidMain/kotlin/org/siloserver/silo/common/player/PlaybackSessionManager.kt).
- [Apple server-provided playback choices](https://github.com/Silo-Server/silo-apple/blob/e9ea909d0c04f3a17b5333210677345715521577/iosApp/iosApp/Screens/Player/ApplePlaybackQuality.swift).
- [Kodi plugin identity preservation](https://github.com/xbmc/xbmc/blob/f8815ee40f49a700c047982d752be4b2a61420e2/xbmc/filesystem/PluginDirectory.cpp), [file state persistence](https://github.com/xbmc/xbmc/blob/f8815ee40f49a700c047982d752be4b2a61420e2/xbmc/utils/SaveFileStateJob.cpp), and [video database modification-date lookup](https://github.com/xbmc/xbmc/blob/f8815ee40f49a700c047982d752be4b2a61420e2/xbmc/video/VideoDatabase.cpp).
- [Kodi VideoPlayer reopen handling](https://github.com/xbmc/xbmc/blob/f8815ee40f49a700c047982d752be4b2a61420e2/xbmc/cores/VideoPlayer/VideoPlayer.cpp), [player-core transitions](https://github.com/xbmc/xbmc/blob/f8815ee40f49a700c047982d752be4b2a61420e2/xbmc/application/ApplicationPlayer.cpp), and [Python callback broadcast](https://github.com/xbmc/xbmc/blob/f8815ee40f49a700c047982d752be4b2a61420e2/xbmc/interfaces/python/XBPython.cpp).
