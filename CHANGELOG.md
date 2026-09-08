# Changelog

## 0.3.0 - 2026-09-08

- Added structured interview rounds with conflict detection, outcomes, reminders, and ICS export.
- Added explainable local JD/resume matching, editable resume text, tags, custom fields, bulk status changes, status undo, duplicate merge, JSON export, templates, clipboard capture, sample data, and dark mode.
- Added a Windows first-run wizard, Docker/API diagnostics, one-click local service start/stop, guided backup, global Ctrl+Shift+N capture, app icon, update-manifest hook, runtime package, and Inno Setup installer definition.
- Embedded a self-contained loopback-only FastAPI service, SQLite database, reminder scheduler, and per-user secret in the Windows package so recipients can install and use JobFlow without Docker, Python, MySQL, Redis, or .NET.
- Fixed the WPF startup crash caused by mutating frozen theme brushes; theme resources now update dynamically in both light and dark modes.
- Kept contacts and referral tracking out of this release by design.

## 0.2.0 - 2026-09-07

- Added Alembic migrations, persistent uploads, backup/restore, health checks, and database startup retry.
- Completed company, job, resume, and application lifecycle operations, including archive/restore and CSV import/export.
- Added timeline-derived funnel, source, resume-version, weekly-trend, and time-to-offer analytics.
- Added Redis/Celery reminders, weekly reports, idempotency, retries, and durable task-failure records.
- Upgraded the MV3 extension with site adapters, editable preview, minimal permissions, and an offline retry queue.
- Added a native .NET 8 WPF desktop client with tray notifications, quick capture, status updates, offline queue, deep links, and optional startup.
- Expanded the desktop client with full application editing, search/filtering, schedules, archives, timelines, company and resume management, CSV transfer, analytics, reminders, account settings, and a configurable API endpoint.
- Changed the Windows desktop release to a self-contained single-file build so recipients can unzip and run it without installing .NET.
- Added backend, React, extension, Playwright, Docker, and desktop CI checks plus Prometheus metrics.
- Fixed the resume upload form reporting a false backend connection error after a successful upload.
- Defined the supported deployment model as per-user local self-hosting and restricted published ports to the loopback interface.
- Added random local secret initialization, Docker context exclusions, pinned dependency constraints, consistent component versions, browser security headers, and immutable baseline migrations.
- Added repository security and contribution guidance, Dependabot configuration, coverage enforcement, release checksums, and packaged desktop verification in CI.
- Expanded backend edge-case and operational tests to 100% line coverage, including authentication failures, upload and CSV limits, Celery failure persistence, and database startup retries.
- Redesigned the WPF desktop experience with a modern high-DPI theme that mirrors the Web palette, plus a refreshed login workspace, consistent cards and controls, clearer hierarchy, and improved empty/status presentation.
- Licensed JobFlow under the MIT License.
