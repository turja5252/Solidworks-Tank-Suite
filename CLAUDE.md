# Elite SolidWorks Automation Suite

Python (pywin32) automation that builds API-650 style tank geometry in SolidWorks 2013 on the computer
named Solidworks. See README.md for the modules and roadmap, and TODO.md for ideas agreed on and
parked for later (add new parked ideas there).

The project rules live in `.cursor/rules/` so Cursor and Claude Code share one copy. Follow them:

@.cursor/rules/repo-workflow.mdc
@.cursor/rules/solidworks-com.mdc
@.cursor/rules/nozzle-engine.mdc

## Running things

- Tests: `python -m pytest` from the repo root (the package is in `src/`; tests run without SolidWorks).
- Lint: `ruff check src tests` (line length 120).
- The app: `Elite SW Auto.bat`. It loads the code once at start, so close and reopen it after a change.
