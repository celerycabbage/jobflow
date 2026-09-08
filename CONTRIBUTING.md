# Contributing to JobFlow

Thanks for helping improve JobFlow. Keep changes focused, describe their user impact, and
include tests for behavior changes.

## Development checks

Run the relevant checks before opening a pull request:

```powershell
cd backend
.venv\Scripts\python.exe -m ruff check app tests
.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm run lint
npm test
npm run build

cd ..\extension
npm run check
npm test

cd ..\desktop\JobFlow.Desktop
dotnet build --configuration Release
```

Never commit `.env`, databases, uploaded resumes, backups, build outputs, access tokens, or
real applicant data. Schema changes require a new Alembic migration; never edit a migration
that has already appeared in a tagged release.
