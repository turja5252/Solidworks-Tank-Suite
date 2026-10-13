# SolidWorks Automation Suite

Python-driven **live menus** that build and update tank geometry in SolidWorks (2013 and newer) on the computer named **Solidworks**.

Inspired by your Elite AutoLISP Tank Properties (ETP) workflow and by how apps like AMETank / Hexagon TANK / SMARTANK organize tank design: **properties → shell courses → 3D model**, then later floors, roofs, nozzles, and drawings.

## Launch

1. Open SolidWorks on the Solidworks computer.
2. Double-click **`Elite SW Auto.bat`** (or **`Elite SW Auto.pyw`**).
3. Use the **Tank Properties** tab.

### Tank Properties (slice 1)

- Diameter + basis (outside / inside / centerline)
- Up to 8 shell courses (height + thickness), bottom → top
- **Create tank shell** → SolidWorks builds a revolved multi-course wall
- Change values with the part still open → shell rebuilds
- **Save / Load** JSON (plus an ETP-style sidecar for future AutoCAD round-trip)

### Live Cylinder tab

Practice parametric create/update (diameter × height).

## Roadmap (AMETank-style modules)

| Phase | Module | Status |
|-------|--------|--------|
| 1 | Tank Properties + live shell | **now** |
| 2 | Floor / annular / chime | next |
| 3 | Roof (cone / rafter types from ETP) | later |
| 4 | Shell nozzles + roof nozzles (from RNC / ROOFNOZZLES) | later |
| 5 | Anchor chairs, FTCO, stairs / platforms | later |
| 6 | Plate stretchout / MS / CNC export | later |
| 7 | API-650 calc reports (optional; separate from geometry) | later |

We are **not** copying AMETank/SMARTANK. We are building Elite’s own SolidWorks tool using your AutoLISP parameter model and the same industry workflow those apps use.

## SolidWorks Macro menu

If **Tools → Macro → New** crashes, that is a VBA/VBE issue on SolidWorks 2013 under newer Windows. Use **Elite SW Auto** (API automation). See `macros\SolidWorks VBA crash note.txt`.
