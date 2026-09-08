# Release checklist

## Before the first public commit

- [x] Choose and add a root `LICENSE` file (MIT).
- [x] Review `git status --short` and confirm `.env`, databases, uploads, backups,
      build output, and test reports are not staged.
- [x] Run a secret scanner or equivalent staged-content review.
- [x] Run `python tools/check-version.py` and confirm every component uses the release version.
- [x] Run every command in the README verification section.
- [x] Add Web and desktop screenshots to the GitHub-facing README.
- [ ] Start from a clean Docker state and complete one register-to-delete-account workflow.
- [ ] Test backup and restore with disposable data.
- [ ] Test the desktop ZIP after extracting it on a clean Windows x64 machine.
- [ ] Test the Inno Setup installer, first-run Docker detection, start/stop, backup,
      uninstall, protocol registration, and upgrade-over-existing-install paths.

## GitHub repository settings

- [ ] Enable private vulnerability reporting, Dependabot alerts, and security updates.
- [ ] Protect `main` and require the CI workflow before merging.
- [ ] Restrict workflow permissions to read-only by default.
- [ ] Pin external GitHub Actions to reviewed full commit SHAs.
- [ ] Add the repository description, topics, and a screenshot or demo image.

## Before tagging

- [ ] Update `CHANGELOG.md` and verify that the tag matches the component version.
- [x] Verify generated ZIP checksums.
- [ ] Review the release artifacts before publishing them.
- [x] Document known limitations, including the local-only deployment boundary and
      the unsigned Windows executable warning.
- [ ] Configure an EV/OV code-signing certificate and `JOBFLOW_SIGN_COMMAND`; verify
      both installer and uninstaller signatures and timestamp before public release.
- [ ] Publish a HTTPS `update.json`, set its URL in release defaults, and test both
      up-to-date and update-available states. Do not ship a placeholder feed.
