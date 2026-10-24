# SolidWorks Automation Suite

Python-driven **live menus** that build and update tank geometry in SolidWorks (2013 and newer) on the computer named **Solidworks**.

Inspired by your Elite AutoLISP Tank Properties (ETP) workflow and by how apps like AMETank / Hexagon TANK / SMARTANK organize tank design: **properties → shell courses → 3D model**, then floors, roofs, nozzles, access, internals, and drawings.

## Launch

1. Open SolidWorks on the Solidworks computer.
2. Double-click **`Elite SW Auto.bat`** (or **`Elite SW Auto.pyw`**).
3. Use the tabs below (Tank Properties first).

### Shipped tabs (today)

| Tab | What it does |
|-----|----------------|
| **Tank Properties** | Diameter + basis, up to 8 courses, plate layout / stagger, live curved shell plates, Save/Load JSON (+ ETP-style sidecar) |
| **Floor** | Lap-welded shoulder plate layout + SolidWorks build |
| **Roof** | Cone roof (bar/angle ring), flat pattern, roof plate layout |
| **Stringer / Tread Joint** | Spiral stair stringer mock + tread joint helpers |
| **Live Cylinder** | Practice parametric create/update |

Spiral stair flights, mid platforms, posts, rails, and braces are in code under `src/swauto/stair/` and still hardening on the Solidworks PC.

## Module catalog (target product)

Not copying AMETank/SMARTANK — Elite’s own SolidWorks tool using your AutoLISP parameter model. Modules below are the intended surface area; status is relative to this repo.

### A — Core geometry (foundation)

| Module | AutoLISP / notes | Status |
|--------|------------------|--------|
| Tank Properties + shell courses | ETP | **shipped** |
| Shell plate layout / stagger | Shell Plate Layout | **shipped** |
| Individual curved shell plates | limited revolve | **shipped** |
| Plate seam sketch (fallback) | Approach A | **shipped** (fallback) |
| Floor / shoulder plates | SOLDIERPLATES-style | **shipped** |
| Annular / chime | floor family | backlog |
| Cone roof + compression ring | GA section | **shipped** |
| Roof plate flat pattern | unrolled cone | **shipped** |
| Other roof types (rafter / dome / …) | ETP roof types | backlog |

### B — Nozzles & openings

| Module | AutoLISP / notes | Status |
|--------|------------------|--------|
| Shell nozzle layout | RNC | backlog |
| Roof nozzles / manways | ROOFNOZZLES | backlog |
| FTCO (flush-type cleanout) | FTCO | backlog |
| Other shell openings (overflow, gauge, etc.) | as needed from lisp suite | backlog |

### C — Access & platforms

| Module | AutoLISP / notes | Status |
|--------|------------------|--------|
| Spiral stair (flights, treads, stringers) | SpiralStairTool / stringer lisps | **active** |
| Stair mid platforms + shell ties | Stair Platform / SpiralShellPlatform | **active** |
| Stair posts / rails / braces | platform & rail lisps | **active** |
| Roof platform | roof access platform | backlog |
| Caged ladder / other access | if in Elite suite | backlog |

### D — Anchors, internals, piping

| Module | Notes | Status |
|--------|-------|--------|
| Anchor chairs | shell base anchors | backlog |
| Internal piping | in-tank pipe runs / supports | backlog |
| Other internals (mixers, heaters, …) | as Elite lisps require | backlog |

### E — Output & calcs

| Module | Notes | Status |
|--------|-------|--------|
| Plate stretchout / MS / CNC export | from layout math | backlog |
| Drawings / GA views | later | backlog |
| API-650 calc reports | optional; keep separate from geometry | deferred |

### Integration spine

| Concern | Status |
|---------|--------|
| Unified tank session (`TankProject` in `src/swauto/tank/project.py`) | **now** — shared shell hub; Floor / Roof / Stringer follow shell OD & height; Save/Load project JSON |
| Same SolidWorks document for attach | partial — floor/roof reuse live shell model when present |
| JSON / ETP round-trip across modules | project JSON (v1) + shell ETP sidecar |

## Suggested build waves

1. **Close stair** — acceptance on Solidworks PC; math tests where possible  
2. **Deepen `TankProject`** — openings/access slots on the same project; one rebuild order on the live part  
3. **Shell nozzles (RNC)** → **roof nozzles** → **FTCO** (shared opening schedule on the project)  
4. **Roof platform** (needs roof + often stair/ladder attachment points)  
5. **Anchor chairs** + **internal piping**  
6. **Export / drawings**; API-650 on its own track  

### Coherent tank (how modules talk)

The app builds one `TankProject` at launch. Tank Properties writes the shell; Floor, Roof, and Stringer subscribe and can **Follow shell** so diameter / top radii / height stay aligned. Builds prefer the live shell SolidWorks document. Use **Save project…** / **Load project…** on Tank Properties for a single JSON covering shell + floor + roof + stair params.

We are **not** copying AMETank/SMARTANK. We are porting Elite’s AutoLISP parameter model into SolidWorks, module by module.

## SolidWorks Macro menu

If **Tools → Macro → New** crashes, that is a VBA/VBE issue on SolidWorks 2013 under newer Windows. Use **Elite SW Auto** (API automation). See `macros\SolidWorks VBA crash note.txt`.
