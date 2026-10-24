# Silo for Kodi

A browsing client for Silo, targeting Kodi 21 on CoreELEC. The intended client uses Silo account authentication and profiles, browses libraries on demand, and delegates media playback to Kodi without syncing the catalog into Kodi's library.

**Status:** authentication milestone in validation. Version `0.1.0` provides manual server configuration, QR sign-in, persistent authentication, and profile selection through a Kodi account screen and a shared headless helper. Library browsing and Silo media playback are not implemented yet.

- [Minimal client design](docs/design.md)
- [Development and target test loop](docs/testing.md)
- [Contributor guidance](AGENTS.md)

```sh
nix develop path:.
python scripts/dev.py check
python scripts/dev.py package
```

The ZIP is written to `dist/`. Follow the test guide for SSH setup and deployment. Local testing references and configuration belong in ignored `.local-testing/`. Internal notes, source snapshots, and raw output belong in ignored `.scratch/`; generated ZIPs belong in ignored `dist/`.
