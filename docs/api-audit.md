# Silo v2 API usage audit

This audit compares the add-on's actions with the deployed `/api/v2/openapi.json` contract inspected on October 24, 2026: **714 paths, 886 HTTP operations, 57 API groups**. Every operation was inventoried and assigned a scope disposition. Request and response contracts were inspected in detail for the add-on's actions and the alternatives identified below. This is a contract and implementation review, not a claim that all 886 operations were executed or exhaustively tested.

The deployment URL, raw schema, digest, per-operation inventory, and device evidence stay in ignored local testing storage. Public references use API paths relative to `/api/v2`. The deployed schema takes precedence over the pinned upstream source where they differ. Keep the handwritten client focused on viewer operations; generating or implementing the entire server API would not improve this client.

## Action-to-contract review

| Add-on action | Contract used | Ownership and result |
| --- | --- | --- |
| Enter server and show style | `/theme/branding` | Manual URL, verified TLS, public accent. No discovery, network provisioning, or admin branding calls. |
| QR sign-in | `/auth/device/capability`, `/auth/device/start`, `/auth/device/poll`, `/auth/device/cancel` | Full `device_login`, not a temporary profile handoff. Browser approves. Respect polling delays and extended expiry; persist the nested one-time token response before announcing success. |
| Maintain login | `/auth/refresh`, `/auth/logout` | Shared locked credential store, stable device ID, atomic writes. Refresh and retry a rejected authenticated request once; PIN verification is not retried. A network failure does not erase credentials. Logout clears local authority even if remote revocation cannot be confirmed. |
| Choose profile | `/profiles`, `/profiles/{id}/verify-pin` | Account-level listing and PIN proof; all subsequent viewer calls carry the chosen profile and proof. No PIN storage, profile creation UI, or account impersonation. |
| Build library sidebar | `/settings/values/effective?keys=ui.disabled_library_ids`, `/user/libraries` | Resolve the effective value, not an authored override. Filter self-hidden libraries: unrestricted library responses can include them. Never substitute admin `/libraries`. |
| Browse library and load more | `/catalog?source=query&library_id=…&type=video&sort=title&limit=50&skip_total=true` | Server cursor controls continuation. Exact totals are unused. `video` means movies and series, appropriate for this grid. |
| Open Home | `/home/layout`, `/home/sections`, `/profile/sections/settings?scope=home` | Prefer layout; unsupported endpoints permit aggregate, then effective-settings discovery. Preserve IDs, visibility, and positions. Default recipe ordering applies only when discovered settings lack positions. Empty layouts remain authoritative. |
| Home rows and View all | `/home/sections/{id}/items`, `/catalog?source=section&scope=home&section_id=…&limit=50&skip_total=true` | Row endpoint gives bounded cards; catalog gives cursor pages. Omit sort to preserve recipe order and omit `type=video` to retain episodes. Refresh rows after playback. |
| Details, seasons, episodes | `/catalog/items/{id}`, `/catalog/series/{id}/seasons`, `/catalog/series/{id}/seasons/{num}/episodes` | Server metadata and opaque identities; season zero is valid. Containers are not playable files. |
| Play/version/resume menu | `/watch/{id}` | One response supplies playable `versions` and profile `user_data`. Avoid a separate versions request in the browser. Saved position is informational for the menu; the start plan selects the actual resume position. |
| Start playback | `/catalog/items/{id}/versions`, `/playback/capabilities`, `/playback/start` | The independent owner retrieves trusted track metadata under its profile, negotiates protocol 3, and sends a stable attempt ID. UI navigation carries IDs, not authoritative track data or credentials. |
| Pause, seek, resume | Kodi player plus `/playback/{session_id}/progress` | Kodi owns controls; send monotonic sequenced samples, including while paused. Seekable original/VOD media does not need a server replan for every seek. |
| Restart | `/playback/start` with `start_position: 0` | No separate progress deletion or local resume database. Normal resume omits this override. |
| Quality/subtitle change | `/playback/{session_id}/replan` | Use offered quality labels and canonical track identities. Stable request ID/body for retries; preserve position, pause, selected audio, and file identity. Returned plan replaces the previous grant. |
| Audio selection | Kodi tracks; selected identity carried into replans | Match native metadata uniquely to source identity. Never equate Kodi ordinal with FFmpeg global stream index. Persistent preference editing is separate work. |
| Stream and seek ranges | Plan-granted `/stream/{session_id}` or transcode manifest/segments | Follow grants rather than construct file/download URLs. Same-origin credentials refresh through the attempt relay. Preserve original bytes and range semantics. |
| Subtitle delivery | Plan-granted `/stream/{session_id}/subtitles/{track}` or negotiated embedded/burn-in decision | Session authorization applies. Stored-subtitle downloads and provider APIs are not replacements for this grant. ASS font bundles exist but are not qualified. |
| Stop/error cleanup | `DELETE /playback/{session_id}` | Stable stop ID and final sample; stop only the owned player, close relay workers, stop the server session, then release profile authority. |
| Account/profile/server change | Local playback ownership lock | Finish playback under its original profile before replacing authority. Never retag an existing session. |

## Changes from the audit

- Home can discover real section IDs through profile settings rather than guessing seed IDs. Aggregate and settings fallback paths pass installed-client checks with endpoint unavailability injected; authentication and transient errors do not trigger fallback.
- The Play menu uses the composite watch response for versions and resume state. The playback owner's separate metadata read remains intentional because it is an independent invocation and must not trust UI-supplied track metadata.
- Library navigation honors effective self-hidden library preferences even for an unrestricted account.
- Cursor browsing sends `skip_total=true`; the add-on has no exact-count UI to justify the counting work.

The API supplies resume, restart, progress persistence, selected quality, subtitle negotiation, and profile switching. These are implementation/qualification responsibilities, not missing-server features. Server progress persistence remains the default; offline `/sync/progress` is unnecessary for this client.

## Follow-up decisions

| Capability | Assessment and next step |
| --- | --- |
| Bundled Home rows | `/home/capabilities` advertises `include_items_max`; only then may `/home/layout?include_items=N` be used. Missing `included_sections` rows require normal row reads. Useful performance follow-up, with response lifetime limited to the current Home refresh. Do not introduce a persistent profile cache. |
| Artwork widths | `/images/capabilities` describes slot-width parameters and cache sizes. Omitted sizing already selects each surface's server default, so it does not imply original-size downloads. Measure those defaults on the target before adding physical-pixel width selection. Never rewrite signed artwork URLs. |
| Remembered audio/subtitles | `/audio-prefs/{series_id}`, `/subtitle-prefs/{series_id}`, `/library-playback-prefs`, and effective settings exist. Watch exposes effective choices and playback negotiates selection. Explicitly saving user choices is client work; define series/item/device scope and reconcile native OSD changes before writing preferences. No parallel local preference database. |
| Library context | Detail/watch/season APIs accept `library_id` to choose presentation when an item belongs to several libraries. The client retains profile authorization but does not yet propagate this presentation context through every screen. Add a multi-library fixture before claiming matching library-specific presentation. |
| Multipart items | Watch exposes `playback_variants` and ordered parts. The initial client selects one file; multipart chaining is not implemented. Do not label this as complete multipart playback. |
| Subtitle appearance/fonts | Effective device appearance and ASS attached-font APIs exist. Kodi owns rendering settings; automatic mapping and font handling need an explicit supported contract and visual qualification. |
| Native OSD subtitle choices | Silo's subtitle menu negotiates changes; direct Kodi OSD subtitle selection is not yet reconciled into subsequent replans or remembered preferences. |
| Network adaptation | Bandwidth probe/results and device connection limits exist. Do not send guessed bandwidth, clear learned limits, or add a startup probe by default. Automatic adaptation remains outside initial scope. |
| Playback control and events | HTTP progress/replan/stop already satisfy the owned playback loop. Control sockets support remote commands; adding an always-on service is not required for local remote-control playback. Route diagnostics explicitly prohibit automatic retry, unlike identity-bound playback mutations. |
| Additional viewer actions | Search, collections, favorites/watchlist, watched toggles, ratings, recommendation feedback, skip markers, and trickplay are available. They are optional UX additions, not substitutes for the core contracts above. |

Capability documents describe support/configuration, not operational health. Do not use capability probes to hide authentication, throttling, or temporary server failures. Retrying is operation-specific: start/replan/progress/stop have identity or sequence contracts; PIN checks and one-time credential collection do not share generic mutation retries. API success does not prove decoder, HDMI, FEL, audio passthrough, or uninterrupted playback.

## Whole-API scope coverage

Counts are HTTP operations, so GET and HEAD are separate operations. Mixed viewer/admin groups are classified at the operation level in the local inventory; the table summarizes their disposition. Excluded operations were reviewed for scope without executing administrative or account-changing requests.

| API group | Operations | Disposition |
| --- | ---: | --- |
| `account` | 10 | Account verification; identity and password management remain in Silo. |
| `admin` | 119 | Server administration; outside the viewer client. No calls added. |
| `admin-ai` | 7 | Server administration; outside the viewer client. No calls added. |
| `admin-autoscan` | 20 | Server administration; outside the viewer client. No calls added. |
| `admin-catalog` | 47 | Server administration; outside the viewer client. No calls added. |
| `admin-collections` | 36 | Server administration; outside the viewer client. No calls added. |
| `admin-nodes` | 11 | Server administration; outside the viewer client. No calls added. |
| `admin-observability` | 19 | Server administration; outside the viewer client. No calls added. |
| `admin-plugins` | 24 | Server administration; outside the viewer client. No calls added. |
| `admin-policy` | 14 | Server administration; outside the viewer client. No calls added. |
| `admin-recommendations` | 6 | Server administration; outside the viewer client. No calls added. |
| `admin-sections` | 11 | Server administration; outside the viewer client. No calls added. |
| `admin-settings` | 30 | Server administration; outside the viewer client. No calls added. |
| `admin-tasks` | 13 | Server administration; outside the viewer client. No calls added. |
| `admin-users` | 31 | Server administration; outside the viewer client. No calls added. |
| `api-keys` | 4 | Not needed for device login; no key administration. |
| `artwork` | 2 | Use returned signed artwork URLs without account headers. |
| `auth` | 24 | Refresh and logout; browser owns password, OAuth, signup, and account recovery. |
| `autoscan` | 2 | Server scanning and source management excluded. |
| `branding` | 4 | Read public branding; artwork upload/administration stays server-side. |
| `catalog` | 27 | Browse, detail, seasons, episodes, versions; search/filter/people/extra surfaces deferred. |
| `collections` | 32 | Optional viewer collection browsing deferred; collection editing/import excluded. |
| `compat` | 1 | Native v2 client; no compatibility-listener discovery. |
| `device-login` | 8 | Capability, start, poll, cancel; approval and denial belong to the browser. |
| `devices` | 4 | Device management is outside initial scope; stable device header is sent. |
| `diagnostics` | 6 | No automatic diagnostic upload; local acceptance evidence only. |
| `downloads` | 25 | Offline/download management excluded; not a substitute for playback grants. |
| `ebooks` | 11 | Outside video playback scope. |
| `favorites` | 4 | Optional personal list controls deferred. |
| `history` | 2 | Optional history browsing/removal deferred. |
| `history-imports` | 8 | No external history import or Kodi library synchronization. |
| `home` | 10 | Layout, aggregate, and section cards used; calendar and editors deferred. |
| `images` | 1 | Optional sizing optimization; retain server surface defaults for now. |
| `invitations` | 9 | Account invitations remain in Silo. |
| `libraries` | 38 | Viewer discovery used; library layouts/collections deferred, administration excluded. |
| `network-access` | 4 | No network discovery, connection provisioning or administration. |
| `not-interested` | 5 | Optional recommendation feedback deferred. |
| `notifications` | 43 | No inbox, push registration, notification delivery or channel configuration. |
| `onboarding` | 4 | Server/account onboarding remains in Silo. |
| `playback` | 31 | Capabilities, start, progress, replan, stop and granted media used; optional control socket, shuffle, markers and network adaptation deferred. |
| `plugins` | 1 | Silo server plugin surfaces excluded. |
| `policy` | 1 | Server playback decisions remain authoritative; no policy editor or local replica. |
| `preferences` | 9 | Server resolves playback preferences; explicit remembered-choice editing deferred. |
| `profile_sections` | 5 | Effective section settings fallback used; layout editing deferred. |
| `profiles` | 8 | List and PIN verification; profile administration remains in Silo. |
| `progress` | 7 | Playback owns progress; standalone clearing and offline synchronization not used. |
| `ratings` | 4 | Optional rating controls deferred. |
| `realtime` | 25 | No watch parties or always-on event connection in initial scope. |
| `recommendations` | 14 | Consume Home recipes; no parallel recommendation engine or taste onboarding. |
| `requests` | 27 | Media acquisition requests and provider-account connections excluded. |
| `scan` | 3 | Server scanning excluded. |
| `settings` | 16 | Effective hidden-library setting used; general editor, plugin settings and subtitle appearance deferred. |
| `subtitles` | 22 | Session grants deliver subtitles; provider search, upload, translation and editing excluded. |
| `system` | 16 | OpenAPI used for audit; manual URL entry, no server setup or discovery. |
| `watch` | 4 | Composite watch read used; manual watched toggles and trickplay deferred. |
| `watchlist` | 7 | Optional personal list controls deferred. |
| `webhook-sync` | 10 | External-provider synchronization excluded. |
## Validation and remaining limits

The revised add-on passes 111 automated tests, Python 3.11 syntax/manifest checks, and ZIP deployment. A target check reads effective library settings, browses a cursor page, reads the composite watch response, and starts an episode through the installed browser's Play/restart flow. The temporary UI test’s forced script shutdown then left Kodi GUI commands unresponsive, so its cleanup/screensaver check did not pass; this is not a clean end-to-end acceptance result. The live default hidden-library value was null; the client treats that as no hidden IDs, covered alongside explicit hidden values. Unit tests distinguish effective values from requested values and cover version selection, resume/restart, cancellation, and stale profile authority.

The Home compatibility device checks simulate unavailable endpoints around live responses; they do not establish compatibility with every older Silo release. No unrelated administrative endpoints were exercised. Broader playback qualification, natural token-expiry playback, multipart support, and the follow-ups above remain separate from this audit.
