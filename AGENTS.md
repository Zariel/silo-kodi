# Silo Kodi development

## Scope and ownership

- Build a browsing add-on for Kodi 21+ on CoreELEC. Silo owns authentication, profiles, catalog visibility, and playback authorization; Kodi owns decoding, seeking, pause, track selection, and HDMI output.
- Do not sync the Silo catalog into Kodi's library or introduce a local catalog database.
- Read `docs/design.md` and `docs/testing.md` before changing the API or playback lifecycle. Keep the first release focused on sign-in, profile selection, library browsing, and original-quality playback.
- Prefer Kodi primitives and Python's standard library. Add dependencies or background services only for a demonstrated contract.
- Keep profile authority attached to the playback session that created it. Never silently downgrade Dolby Vision or claim FEL support from codec names or EDID alone.

## Workflow

- Use `jj` for version control. Make small logical commits. Pass complete commit messages through `format-commit-message` and then `jj describe --stdin`; never put messages in command-line arguments.
- Keep all internal hostnames, addresses, deployment references, target inventories, and local testing configuration in ignored `.local-testing/`. Never include them in tracked files or commit messages.
- Use `.scratch/` for internal notes, upstream checkouts, credentials, and raw device output. It is ignored. Build artifacts belong in ignored `dist/`. Never commit tokens, pairing codes, logs with media URLs, or credentials.
- Use the pinned Nix development shell, or Python 3.11 with only the standard library. The target has Python 3.11; avoid newer syntax and APIs.
- Run `python scripts/dev.py check` and `python scripts/dev.py package` after add-on changes. Exercise meaningful behavior through Kodi on the target; mocked Kodi calls alone do not prove playback.
- Do not restart Kodi or interrupt existing playback as part of a routine deployment. Check active players first. Keep test assets and backups outside the installed add-on directory.
- Preserve unrelated changes and do not change cluster deployment, HDMI, audio, or CoreELEC configuration to make tests pass.

## Design and validation

- Before an expensive architectural decision, establish constraints and compare materially different ownership models. Reopen the decision if new evidence changes those constraints.
- Repeated failures of the same invariant require an audit of every owner of that responsibility before an isolated fix.
- Prefer small internal APIs, concrete values, precise names, and comments that explain non-obvious ordering or ownership.
- Test observable contracts with independent expected results. Validate the complete stateful workflow, including repeat operation and cleanup, when relevant.
- Separate measured results from inferred capabilities and untested requirements. Never equate a successful HTTP response or player start with HDR, FEL, passthrough, or sustainable bitrate validation.
