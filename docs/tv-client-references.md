# TV browsing references

The Kodi browser uses a 1920×1080 design canvas that Kodi scales to the configured GUI resolution. Density is a layout choice: the library and search grid has eight columns with the compact rail (six with the expanded menu) and three complete rows plus a clipped preview of the next row at either output resolution. Episode lists also show part of the next item. Home retains two complete server-defined horizontal shelves and previews the next non-empty shelf below them. The preview disappears at the end and becomes a complete shelf when navigating down. Detail text and actions use smaller type and tighter spacing.

## Official client review

The source review used these upstream revisions, without importing their UI frameworks or copying implementation code:

- [Silo Android TV](https://github.com/Silo-Server/silo-android/tree/51e480a409f0bed9b7c4b3d92e335876da4030db/androidTvApp): `TvMediaCardActions.kt` provides play, watched, favourite, watchlist, and Home removal actions on a card hold. `TvSearchViewModel.kt` scopes search to media the TV client can present and preserves server-owned search behavior. `TvMainShell.kt` uses top-level navigation and secondary personal destinations.
- [Silo Apple TV](https://github.com/Silo-Server/silo-apple/tree/e9ea909d0c04f3a17b5333210677345715521577/iosApp/iosApp/tvOS): `TVMediaCard.swift` attaches personal-state actions to cards with catalog identity and profile state. Its focus treatments include a clear poster ring. The detail screens separate the hero, actions, facts, cast, and seasons into focused components.

Adopt the card action vocabulary, profile-owned state, clear focus, and compact metadata. Retain Kodi's existing sidebar and native keyboard/dialog primitives instead of duplicating either native client's full navigation shell. People search, remote discovery results, requests, downloads, and administrative actions remain outside this change.

## Sidebar behavior

Home starts with the sidebar expanded. The first Up, Down, or Right enters the first shelf and collapses the sidebar; Left keeps the sidebar available for normal menu navigation. Returning to the sidebar with Left lets Up and Down select its entries.

Preload all Home shelves before changing the visible controls, using the aggregate sections response in layout order. Fall back to individual section reads only when necessary. Vertical navigation reuses this in-memory snapshot; returning from details reuses cached catalog responses; playback return and personal actions invalidate those responses before refreshing. Bind each complete card list in one batch. Keep the old shelves visible on a slow or failed fetch, and preserve explicit sidebar navigation during loading.

All browser views live inside one content group. `_BrowserLayout` owns the sidebar inset, flexible control widths, and menu input bounds. The expanded sidebar reserves 360 design pixels; the compact rail reserves 120. Content coordinates are relative to that region, and resizing preserves the right margin and intrinsic poster/button sizes. Kodi reflows grid columns while horizontal shelves retain their card widths. Episode rows fit the minimum available width so their text is never clipped by a smaller container.

The layout owner derives its state from window focus and publishes `sidebar_expanded` after positioning the content. XML uses that state for the menu background, labels and list layouts; it does not independently expand an overlay. Expansion shrinks and moves content before revealing the menu. Collapse hides the menu and moves content before widening controls. The compact menu's input bounds are limited to the icon rail. No fade or slide animation introduces another geometry state. Kodi owns list selection and scrolling, and the same layout policy applies to Home, sections, libraries, search, and movie/series/season details.

## Search and title actions

Search uses `GET /catalog` with `source=query`, `q`, a 50-item page, and the returned opaque cursor. Omit `sort` to retain the server's ranking. Discover `video_with_episodes_scope` through `/catalog/search/capabilities`; use `video` when that capability is absent or the capability endpoint is unsupported. Authentication and transport errors remain errors. Search is scoped to the active profile, and returning from details preserves its results and selection.

Kodi's context-menu action opens options for the focused title. Physical hold-to-menu behavior belongs to Kodi's remote keymap; keyboard **C** or a mapped Menu key also opens it. The menu reads `/catalog/items/{id}` for fresh `user_state`, then offers watched/unwatched, favourites, and watchlist actions only when those flags are present. Series watched actions explicitly say they affect all episodes. Mutations use `/watched/{id}`, `/favorites/{id}`, and `/watchlist/{id}`, under the originating profile; a fresh detail read confirms the requested state before updating the screen. Cancellation makes no mutation. Home progress cards also offer **Remove from Continue Watching** or **Remove from Next Up**. Only `continue_watching`, `in_progress`, and `next_up` rows expose these actions, including their **View all** pages. Use the observed card's `progress_updated_at` for Continue Watching, otherwise its `series_id` for Next Up, matching Android TV's `HomeDismissal` policy. Send `PUT /home/dismissals/{surface}/{item_id}` with that anchor under the active profile. A dismissal does not mark the title watched. Silo removes a dismissed episode's whole show from both progress rows until playback or an undismissal restores it.

Refresh membership from Silo after an action. Replace a section's page identity and cursor when refreshing so an older in-flight page cannot reinsert removed cards. Home refreshes its visible shelves and keeps focus on an available card. Sidebar controls and season containers do not target the detail title's personal actions. No deletion, server administration, or custom global keymap is introduced.

Keep upstream snapshots, screenshots, fixture identities, and raw acceptance output in ignored local storage.


## Home horizontal paging

Continue Watching, In Progress, and Next Up have no **View all** card. Their first catalog page replaces the recipe-limited card list, retaining the section metadata and opaque cursor. The shared pager fetches a page plus one screen ahead, appends unique content IDs without moving selection, and rejects results or errors belonging to a replaced page, shelf, or profile. Home navigation keeps loaded pages in memory. A refresh fetches enough pages to restore the previously selected card when it remains present; repeated cursors terminate paging. Kodi owns artwork loading from the supplied URLs.


## Browsing caches and artwork preparation

A browser's Catalog keeps up to 128 response snapshots for five minutes, bound to its originating profile. Reads return independent copies so paging and UI state cannot modify the cached response. Mutations clear the cache and advance its generation: an earlier in-flight read cannot repopulate an invalidated cache. Playback/window restoration clears it before refreshing. Watch requests and personal-action detail reads always go to the server; cached detail metadata is only for display.

The browser supplies poster, backdrop, and episode-still widths based on Kodi's GUI scale. It eagerly warms Kodi's persistent texture cache through `xbmcvfs.File(image://...)`, using two workers and preserving each signed URL intact. Home prioritizes the first screen of every shelf before the remaining cards; grids enqueue their fetched pages. Kodi owns decoding, persistent cache storage, concurrent-image deduplication, and normal rendering retries. Closing the window cancels pending warm-up work. The add-on does not create a second image store or attach account credentials to artwork requests.

Routine browsing has no loading label. Existing content remains visible while fetching, and grids bind each page in a batch. Request failures still provide an error message.
