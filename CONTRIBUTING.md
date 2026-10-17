# Contributing to TraceHold

Thank you for your interest. TraceHold is a decision-support prototype built for ExaThon India 2026. Issues and pull
requests are welcome.

## Ground rules

- **Synthetic data only.** Never add real, employer or proprietary data, or anything that identifies a real person.
- **No model touches a figure.** AI may only read letters, answer questions over results views, or reword a finished
  letter. Every number comes from SQL in Exasol and must pass the conservation check.
- **Source data and history are protected.** Analysis SQL may only create or drop its own calculation tables; the
  engine's guard (`check_statement` in `backend/app/engine.py`) and Exasol privileges enforce this.
- **Neutral language.** Nothing in the product may accuse or label an account holder.

## Getting set up

Follow the [README](README.md): Installation, then Running TraceHold.

## Before opening a pull request

```powershell
cd backend
..\.venv\Scripts\python -m pytest tests        # all tests must pass
cd ..\frontend
npx tsc --noEmit -p .                          # no type errors
npm run build
```

If you change an analysis SQL file in `database/`, also run a full analysis (`python -m app.engine`) and
`python -m app.evaluation`, and check that conservation still passes for every case.

## Where things live

| Folder | What |
|---|---|
| `database/` | All SQL that runs inside Exasol |
| `backend/app/` | API, engine orchestration, protection layer, live analysis |
| `backend/app/ai/` | AI at the edges and its rule checks |
| `backend/generator/` | Synthetic data, letters and the independent answer key |
| `backend/tests/` | pytest suite |
| `frontend/src/` | The website |

## Licence

By contributing you agree that your contribution is licensed under the [MIT licence](LICENSE).
