# Package and release the add-on

Install the generated add-on ZIP through Kodi's **Install from zip file** option. For local development, use the [SSH deployment loop](testing.md) to replace the installed code while preserving account data.

## Build locally

From the repository root, with Python 3.11 or the pinned development shell:

```sh
python scripts/dev.py check
python scripts/dev.py package
```

The build writes `dist/plugin.video.silo-VERSION.zip` and a matching `.zip.sha256` file. `VERSION` comes from `plugin.video.silo/addon.xml`. Identical inputs produce identical ZIP bytes. A device upgrade check verifies byte-for-byte reproducibility, installed files against the archive, unchanged saved session data and permissions, and successful account access after deployment. Packaging includes only the add-on file allowlist; local credentials, test references, and source snapshots stay outside the archive.

## Publish a GitHub Release

1. Update the manifest version and document the supported behavior and remaining limitations. Complete the applicable device acceptance checks before describing a build as stable.
2. Run the local checks and package with `--release-tag vVERSION`, replacing `VERSION` with the manifest version. A mismatch fails before replacing the ZIP.
3. Commit the release changes using JJ and push the intended revision and its `vVERSION` tag to GitHub.
4. Publish a GitHub Release for that tag. The **Release ZIP** workflow checks the tagged source, verifies the version, and attaches the ZIP and checksum to that release.
5. Confirm the workflow succeeded and both assets appear on the release. Download the ZIP and checksum, verify the digest, and test installation or upgrade in Kodi.

The workflow does not publish a release itself. Publishing the release triggers asset generation, so assets appear only after the job succeeds. Existing assets cause upload to fail instead of being overwritten. Inspect a failed run before changing any published assets.

The **Check and package** workflow also runs on pull requests and pushes to `main`. Its downloadable artifact wraps the add-on ZIP and checksum; extract that wrapper before installing the add-on ZIP in Kodi. Local checks and workflow linting do not prove that a workflow has run successfully on GitHub.

GitHub Releases provide manual downloads. This project does not yet publish a Kodi repository feed for automatic updates.
