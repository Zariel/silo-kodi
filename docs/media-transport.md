# Renew media credentials without reopening playback

Status: integrated for original HTTP media and supported text sidecars. Forced-rotation device acceptance passes; natural-expiry and sustained-bitrate qualification remain pending.

## Requirement

Playback must survive account access-token rotation, including a subsequent seek or resumed range read. Silo requires current account and profile headers on media requests. Its `header_refresh: none` means the media URL remains stable, not that its bearer token never expires. API-token refresh alone does not update the header options already handed to Kodi.

Preserve original media bytes, range semantics, the selected profile, and Kodi's ownership of decoding and HDMI output. Do not change server token lifetimes or bypass media authorization. Renewal must not require a new playback session or reset watch progress.

## Alternatives and decision

| Approach | Assessment |
| --- | --- |
| Leave the initial headers attached to Kodi's URL | Cannot satisfy new media requests after token expiry |
| Refresh headers through a native player facility | No such facility has been established for Kodi's ordinary HTTP playback path; do not declare support based on a different input-stream engine |
| Reopen the same media URL with fresh headers | Requires handling old/new player callbacks, preserving position and track choices, restoring pause, and verifying output recovery; introduces a player transition for a transport credential change |
| Relay authorized media over loopback | Refreshes authority at each upstream request without reopening Kodi; adds responsibility for HTTP forwarding and transfer cleanup |
| Change the server's authorization or token lifetime | Outside the client's scope and would not handle revocation or profile authority correctly |

Implement a scoped loopback relay for original HTTP media and supported subtitle sidecars. Keep it inside the existing playback owner's lifetime. Do not add a persistent service, catalog state, transcoder, or general-purpose proxy.

Revisit this choice if transfer cancellation cannot be bounded, if the target cannot sustain representative bitrate peaks, or if a supported Kodi facility can update media authority without a playback transition.

## Ownership and transport contract

The playback invocation creates an ephemeral listener bound to `127.0.0.1`. An unpredictable per-attempt path maps to a fixed, validated resource from that attempt's plan. Requests cannot supply an upstream URL, override account headers, or access another attempt. Keep the loopback path and remote credentials out of logs.

For each GET or HEAD, obtain authority through the shared session store using the attempt's immutable profile ID. The store already serializes refresh and persists rotated credentials. Release its lock before transferring media so a slow read cannot block progress reporting. Merge current authority with the plan's required headers, retain signed query parameters, verify upstream TLS, and refuse redirects and unapproved origins.

Forward range and conditional-range requests without parsing media or changing bytes. Preserve the relevant status, content length, content range, type, validators, and range support. Request identity encoding. Never turn a partial upstream read into a successful complete response or expose an upstream error body containing private details. Do not replay a partially delivered response from its beginning.

Bound memory and concurrent transfers. Cancellation must close both sides of each active transfer. Shutdown must stop accepting requests, interrupt active transfers, and finish workers before releasing playback authority. Merely stopping the listening socket or making workers daemon threads is insufficient. A failed connection or credential refresh must remain bounded and must not restart an ended attempt.

The existing final cleanup remains responsible for stopping only its owned Kodi playback and closing the Silo session. The relay does not report progress, choose another profile, or create replacement sessions.

The relay can replace its resource map after a validated replan. Validate every resource before publishing the replacement; an invalid resource leaves the previous map intact. Keep the local video path stable so subsequent range requests use the replacement grant. Existing transfers finish against the resource they opened. Give each selected subtitle artifact a distinct local filename to avoid reusing Kodi's cached subtitle content, and remove retired subtitle resources. The playback owner must apply this operation; a UI must not change relay resources directly. This transport operation is implemented but not yet connected to the playback controls.

HLS manifests, segment authorization, and quality replans need a separate extension of this contract. Do not advertise those deliveries merely because original byte ranges work through the relay.

## Evidence and acceptance

An ignored target prototype compared an eight-MiB direct read with a relayed read: status, content range, length, and SHA-256 matched. A real token refresh changed the authority used by the next successful suffix-range request. HEAD preserved the source length. Short throughput samples show feasibility, not sustained bitrate qualification. Private measurements and fixture identities remain outside version control.

The integrated add-on passes the real-video smoke loop. Target checks also confirm selected text subtitles, a 60-second pause, resume and seeking after real credential rotation, and preservation of the new video during external replacement. The playback identity stays unchanged across rotation. A controlled upstream verifies range responses, current authority on new requests, profile rejection, redirect refusal, truncation, concurrency, and transfer cancellation. These tests do not prove behavior across natural expiry or maximum bitrate.

An API-and-transport check on the target verifies subtitle On and Off replans within one session. After each resource replacement, the unchanged local video URL returns matching original bytes. The selected WebVTT artifact is readable; after Off, its retired URL returns 404. This check does not open Kodi playback and therefore does not establish mid-playback subtitle rendering or remote-menu behavior.

Release qualification must cover:

1. Test prefix, suffix, open-ended and unsatisfiable ranges, HEAD, truncated transfers, and concurrent requests through the public loopback interface.
2. Reject an old credential at a controlled upstream, rotate credentials through the shared session, and prove the next read uses the new authority without changing the playback URL.
3. Exercise profile rejection, upstream redirects, unknown local paths, stop during reads, client disconnects, and shutdown with stalled workers. Independently verify listener closure and worker termination.
4. Run the real-video smoke loop through the relay, including subtitles, a long pause, seeks, replacement, and cleanup. Verify Silo progress independently.
5. Qualify playback across natural token expiry and sustained high-bitrate peaks before claiming long-session or maximum-bitrate support. HDR and lossless audio qualification still require the complete output chain.

## References

- [Silo header-authenticated media contract](https://github.com/Silo-Server/silo-server/blob/489fe4d55735f3855b2a0d6276e57d148891b456/docs/architecture/playback-protocol-v3.md#41-header-authenticated-media-urls).
- [Python 3.11 HTTPS connections](https://docs.python.org/3.11/library/http.client.html#http.client.HTTPSConnection).
- [Python server shutdown and worker lifetime](https://docs.python.org/3.11/library/socketserver.html#socketserver.ThreadingMixIn).
