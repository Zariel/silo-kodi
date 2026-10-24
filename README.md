# Silo for Kodi

A browsing client for Silo, targeting Kodi 21 on CoreELEC. The intended client uses Silo account authentication and profiles, browses libraries on demand, and delegates media playback to Kodi without syncing the catalog into Kodi's library.

**Status:** playback in validation. Version `0.3.0` provides QR sign-in, profile selection, library and detail screens, native video playback with Silo progress reporting, quality selection, and text subtitle selection. Representative movies, episodes, pause, resume, start-over, combined subtitle/quality changes, HDR10, and Dolby Vision with receiver-confirmed TrueHD/Atmos pass short checks on the test device. Natural token expiry, sustained bitrate, broader device/output coverage, and additional subtitle formats still need qualification.

Original-file presentation is delegated to Kodi, with declared codec eligibility up to 2160p. HDR, Dolby Vision/FEL, and audio passthrough depend on the device, Kodi build, and configuration. See the compatibility evidence below; these are not universal Kodi support claims.

During playback, return to Silo's browser and choose **Now playing → Subtitles** to select a server-provided text track or **Off**. **Now playing → Return to video** restores fullscreen playback. Kodi's normal controls remain available for pause, seek, and audio.

Choose **Now playing → Quality** for Silo's available qualities or **Auto**. Changing quality preserves position and pause while reopening the video. The initial transcoded path supports SDR H.264/AAC HLS; other delivery combinations remain unqualified.

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
