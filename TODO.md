# To do

Ideas agreed on and parked for later. Newest first.

## Structural package (listed 2026-10-28)

Done first, the same day: the Stairway tab sizes the stair from the full height (floor to top of
shell) with top and bottom offsets, like the lisp launcher; it climbs clockwise or counterclockwise;
and either end can be set to an orientation. Then, also done: the stringer splitter (pieces, splice
plates and their bolt holes, as the lisp's SPLITSTRING), the Stretchout tab (shell plates and seams
with the stair, nozzles, FTCOs and anchor chairs on them, clashes listed; and the developed stringers
as burn pieces), RNC's inside (break) flange on shell nozzles, roof nozzles, rafter roof framing with
the dollar plate and column, and anchor chairs. Still to do:

- **Counterclockwise built natively**, not mirrored (agreed: after clockwise is fully proven).
- **Splitter rounds in 3D**: the lisp's R1 reliefs at the inner stringer's acute joint corners, and the
  inner splice plate's rounded top corner, are on the Stretchout tab's stringer sheet but not in the
  SolidWorks pieces (square there), so a flat pattern exported for burning lacks them. Also slow: a
  6-tread flight split once took 22 min of a 38 min build (2026-10-28, RDP disconnected), mostly the
  eight splice holes, one jig each.
- **Radial platform.** What it is still to be described.
- **Top platform**: today it is the mid-platform frame set past the top tread.
- **Rafter sections**: the lisp's rafters are plain W x h boxes; real shapes (C, W, angle), which way
  they face, and the seats and clips at the shell and at the dollar plate are not in the lisp.
- **External rafter roofs' plates**: the lisp lays them as pies (two rafters each) and a center fill;
  the app still lays its own plate courses.
- **Anchor chair sizes**: the lisp's defaults put the bolt hole off the top plate; get Elite's
  standard chair. Bolts and nuts are not modeled.
- **Roof nozzles**: manways (class 4), 30 in and 36 in sizes, and roof nozzles in the project assembly.

## Hand edits to project parts (parked 2026-10-28)

A project shares one part file between identical pieces, so a hand edit to that file
changes every place it is used. Today the app does not notice hand edits: a part keeps
showing "built", and if its inputs change later, Build changes rebuilds it and the
engineer's own features are left on the new geometry (they may fail or land wrong).
Rebuild all does that to every part. A component moved by hand in the assembly is put
back on the next build.

1. **Detect hand edits.** Record a fingerprint of each part *file* when the app builds it.
   If the file has changed since, the Project tab shows "edited by hand", and Build
   changes asks before touching it: keep the edits, rebuild (losing them), or make a copy.
2. **Make one placement its own part.** Pick a placement; the app copies the shared file
   to its own name (e.g. `Shell C1 Plate A P3 custom`), points that one placement at it,
   and never rebuilds it on its own. The other placements keep sharing.
3. **Optional: Protect built parts.** A setting that marks generated part files
   read-only, so SolidWorks warns before a shared part is saved. Unlock it to change
   every copy, or make it its own part to change one.

Agreed: 1 and 2 for sure; 3 to decide when we get there.

## Also parked

- **Preview (one part) button** on the Project tab: build the whole tank from the project's
  inputs into one part with today's builders, beside Build assembly.
- **Floor and Roof as project parts** (Phase 3), then the **Stairway** (Phase 4: split the
  stair build into pieces; treads, posts and clips share files).
- **Nozzle / FTCO clearance check:** warn when a nozzle lands on an FTCO.
- **FTCO bolts, nuts and washers** (the AMETank model has them).
- **FTCO Left anchor:** check on a model which edge "Left" puts the seam on, looking from outside;
  flip in one line if needed.
- **Default annular thickness** for the FTCO bottom-plate bevel (0 now, so no bevel unless typed).
- **Unused part files:** the build lists them; maybe offer to delete them.
- **Faster builds:** try turning off graphics and feature-tree updates while building (test on SW 2013 first).
  Timed 2026-10-28, a 3-tread stair with no shell: 91 s (the same build took 9.5 min an hour earlier, so the
  machine's state matters too). Outer stringer end holes 27 s, inner 9 s, each tread's bolts 2.5-3 s a side,
  each tread copy 1.4 s, each stringer cut about 3 s.
