# Silo for Kodi

A browsing client for Silo, targeting Kodi 21 on CoreELEC. The intended client uses Silo account authentication and profiles, browses libraries on demand, and delegates media playback to Kodi without syncing the catalog into Kodi's library.

**Status:** playback in validation. Version `0.3.0` provides QR sign-in, profile selection, library and detail screens, original SDR video playback with Silo progress reporting, and text subtitle selection. Representative movies, episodes, pause, resume, start-over, and subtitle On/Off changes work on the test device. Natural token expiry, sustained bitrate, HDR, lossless output, quality selection, and additional subtitle formats still need implementation or qualification.

During playback, return to Silo's browser and choose **Now playing → Subtitles** to select a server-provided text track or **Off**. **Now playing → Return to video** restores fullscreen playback. Kodi's normal controls remain available for pause, seek, and audio.

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
