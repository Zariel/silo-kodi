# Silo for Kodi

A browsing client for Silo, targeting Kodi 21 on CoreELEC. The intended client uses Silo account authentication and profiles, browses libraries on demand, and delegates media playback to Kodi without syncing the catalog into Kodi's library.

**Status:** playback in validation. Version `0.3.0` provides QR sign-in, profile selection, Home, library and detail screens, native video playback with Silo progress reporting, quality selection, and text/embedded PGS subtitle selection. Representative movies, episodes, pause, resume, start-over, combined subtitle/quality changes, HDR10, and Dolby Vision with receiver-confirmed TrueHD/Atmos pass short checks on the test device. A ten-minute high-bitrate playback check passes sampled clock and buffering checks. Natural token expiry, broader bitrate/output coverage, and additional subtitle formats still need qualification.

Original-file presentation is delegated to Kodi, with declared codec eligibility up to 2160p. HDR, Dolby Vision/FEL, and audio passthrough depend on the device, Kodi build, and configuration. See the compatibility evidence below; these are not universal Kodi support claims.

Home opens after profile selection and shows server-ordered rows using your configured accent. Use **View all** to browse a section, or choose a library from the sidebar. Returning from details refreshes the visible rows and retains the selected card when it still exists.

The [six-milestone delivery plan](docs/design.md#delivery-sequence-and-acceptance) includes making Silo Home the main page after playback quality and subtitles, using server-provided sections and ordering, with aggregate Home and profile-section-settings fallbacks.

During playback, return to Silo's browser and choose **Now playing → Subtitles** to select a supported text or embedded PGS track, or **Off**. PGS uses native rendering for original MKV playback and server burn-in for supported lower-quality HLS. Use this menu for subtitle changes; selections made directly in Kodi’s subtitle OSD are not yet reconciled with Silo on a replan. **Now playing → Return to video** restores fullscreen playback. Kodi's normal controls remain available for pause, seek, and audio.

Choose **Now playing → Quality** for Silo's available qualities or **Auto**. Changing quality preserves position and pause while reopening the video. The initial transcoded path supports SDR H.264/AAC HLS; other delivery combinations remain unqualified.

Audio selected through Kodi's controls is carried across quality and subtitle changes when the source track can be matched uniquely. A nondefault soundtrack passes an original → 360p → Auto check. Ambiguous track metadata can prevent a playback change; the add-on reports this instead of guessing a soundtrack.

- [Minimal client design](docs/design.md)
- [Development and target test loop](docs/testing.md)
- [Packaging and GitHub Releases](docs/releases.md)
- [Playback references and compatibility status](docs/playback-references.md)
- [Contributor guidance](AGENTS.md)

```sh
nix develop path:.
python scripts/dev.py check
python scripts/dev.py package
```

The ZIP is written to `dist/`. Follow the test guide for SSH setup and deployment. Local testing references and configuration belong in ignored `.local-testing/`. Internal notes, source snapshots, and raw output belong in ignored `.scratch/`; generated ZIPs belong in ignored `dist/`.

The [API usage audit](docs/api-audit.md) covers the complete v2 endpoint inventory, current actions, and deferred capabilities.
