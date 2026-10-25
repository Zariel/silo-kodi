# TV browsing references

The Kodi browser uses a 1920×1080 design canvas that Kodi scales to the configured GUI resolution. Density is a layout choice: the library and search grid has eight columns and three complete rows plus a clipped preview of the next row at either output resolution. Episode lists also show part of the next item. Home retains two complete server-defined horizontal shelves and previews the next non-empty shelf below them. The preview disappears at the end and becomes a complete shelf when navigating down. Detail text and actions use smaller type and tighter spacing.

## Official client review

The source review used these upstream revisions, without importing their UI frameworks or copying implementation code:

- [Silo Android TV](https://github.com/Silo-Server/silo-android/tree/51e480a409f0bed9b7c4b3d92e335876da4030db/androidTvApp): `TvMediaCardActions.kt` provides play, watched, favourite, watchlist, and Home removal actions on a card hold. `TvSearchViewModel.kt` scopes search to media the TV client can present and preserves server-owned search behavior. `TvMainShell.kt` uses top-level navigation and secondary personal destinations.
- [Silo Apple TV](https://github.com/Silo-Server/silo-apple/tree/e9ea909d0c04f3a17b5333210677345715521577/iosApp/iosApp/tvOS): `TVMediaCard.swift` attaches personal-state actions to cards with catalog identity and profile state. Its focus treatments include a clear poster ring. The detail screens separate the hero, actions, facts, cast, and seasons into focused components.

Adopt the card action vocabulary, profile-owned state, clear focus, and compact metadata. Retain Kodi's existing sidebar and native keyboard/dialog primitives instead of duplicating either native client's full navigation shell. People search, remote discovery results, requests, downloads, and administrative actions remain outside this change.

## Sidebar behavior

Home starts with the sidebar expanded. The first Up, Down, or Right enters the first shelf and collapses the sidebar; Left keeps the sidebar available for normal menu navigation. Returning to the sidebar with Left lets Up and Down select its entries.

Fetch Home shelves before changing the visible controls, then bind each complete card list in one batch. Keep the old shelves visible on a slow or failed fetch, and preserve explicit sidebar navigation during loading.

Keep the content canvas stationary. The expanded rail overlays the left edge instead of shifting every card, label, and button on each focus transition. Use separate native list layouts for expanded labels and the compact selection marker, with identical row heights. Icons remain part of the native list items; Kodi owns scrolling and selection. A short opacity transition emphasizes navigation focus. Icons use 128-pixel assets for scaling, with paths rooted in the add-on.

## Search and title actions

Search uses `GET /catalog` with `source=query`, `q`, a 50-item page, and the returned opaque cursor. Omit `sort` to retain the server's ranking. Discover `video_with_episodes_scope` through `/catalog/search/capabilities`; use `video` when that capability is absent or the capability endpoint is unsupported. Authentication and transport errors remain errors. Search is scoped to the active profile, and returning from details preserves its results and selection.

Kodi's context-menu action opens options for the focused title. Physical hold-to-menu behavior belongs to Kodi's remote keymap; keyboard **C** or a mapped Menu key also opens it. The menu reads `/catalog/items/{id}` for fresh `user_state`, then offers watched/unwatched, favourites, and watchlist actions only when those flags are present. Series watched actions explicitly say they affect all episodes. Mutations use `/watched/{id}`, `/favorites/{id}`, and `/watchlist/{id}`, under the originating profile; a fresh detail read confirms the requested state before updating the screen. Cancellation makes no mutation. Home progress cards also offer **Remove from Continue Watching** or **Remove from Next Up**. Only `continue_watching`, `in_progress`, and `next_up` rows expose these actions, including their **View all** pages. Use the observed card's `progress_updated_at` for Continue Watching, otherwise its `series_id` for Next Up, matching Android TV's `HomeDismissal` policy. Send `PUT /home/dismissals/{surface}/{item_id}` with that anchor under the active profile. A dismissal does not mark the title watched. Silo removes a dismissed episode's whole show from both progress rows until playback or an undismissal restores it.

Refresh membership from Silo after an action. Replace a section's page identity and cursor when refreshing so an older in-flight page cannot reinsert removed cards. Home refreshes its visible shelves and keeps focus on an available card. Sidebar controls and season containers do not target the detail title's personal actions. No deletion, server administration, or custom global keymap is introduced.

Keep upstream snapshots, screenshots, fixture identities, and raw acceptance output in ignored local storage.
