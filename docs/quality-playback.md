# Select playback quality without losing position

Status: the target plays a server-negotiated SDR H.264/AAC transcode through Kodi's native HLS player and the authenticated relay, including seeking after credential rotation. Quality replans are implemented and checked against the server; quality controls and player transition integration are not implemented. Production capabilities still advertise original HTTP only.

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

Kodi broadcasts player callbacks to all registered Python Player instances, and their signatures omit the file identity. Give each intended delivery transition a distinct local video URL and compare the observed current file against that expected URL. The same-core VideoPlayer reopen path emits Started and AVStarted without an intervening Stopped/Ended pair; a core replacement can emit Stopped. Do not require one fixed callback sequence. Keep a bounded pending transition until the expected URL reaches A/V readiness, and preserve the original plugin route on its ListItem for bookkeeping.

After readiness, restore the plan's player position, wait for the observed clock to settle, apply the subtitle decision, and restore pause. Do not report startup zero as a new watch position. Only publish the completed UI selection after the player reaches the intended state. If the committed plan cannot be opened, report the failure and clean up the owned session rather than continuing with stale server identity.

## Evidence and remaining acceptance

A target API probe advertised experimental HLS support without changing installed capabilities. The server returned six fixed rungs for the selected SDR fixture. Selecting its 360p entry returned `server_transcode_hls`, a full timeline, and a finite authenticated media playlist. A separate temporary script opened a fresh 360p plan in Kodi's native player, sought to 90 seconds, observed clock advancement, then stopped and closed the session. No InputStream Adaptive configuration or device output settings changed.

This establishes native-engine feasibility only. It does not establish the integrated quality menu, credential renewal across segments, pause restoration, continuous quality switching, natural expiry, or high-bitrate output.

A subsequent target probe used the relay for the playlist and segments, paused, rotated the real access credential, sought to nine minutes, and observed advancing playback and media requests with fresh authority. Controlled-origin tests independently reject stale authority and verify query preservation, rewritten HEAD length, retired references, and late responses after a replan. Integrated quality transitions and natural expiry remain unqualified.

The shared replan implementation has also been exercised against the server: original to 360p at 120 seconds, subtitle Off retaining 360p, and Auto returning to original at 125 seconds. The returned plans preserved the requested start positions, and the probe closed its session. This checks the negotiation contract without opening Kodi playback; it does not qualify player transitions. Focused tests cover unknown labels, stable retries, track preservation, quality persistence across subtitle changes, and rejection of an anchored HLS timeline while retaining the committed plan for cleanup.

The probe also established a source-identity requirement. On every ListItem used to reopen playback, preserve the genuine originating plugin route in `original_listitem_url`. Kodi otherwise treats the temporary relay URL as a file when persisting watched state, a bookmark, and stream details. Each path can query the file modification date, producing three HTTP HEAD requests during shutdown. Plugin identities skip those modification-date lookups. The target's native stop completed in 0.28 seconds with the property preserved; relay and session cleanup then completed normally. Normal plugin resolution supplies this property, but a direct `Player.play` reopen must retain it explicitly.

Acceptance must cover:

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
