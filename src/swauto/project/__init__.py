"""Projects: a tank built part by part into an assembly.

Every fabricated piece is its own part file in the project folder; identical
pieces share one file placed several times. The project file keeps the inputs
and a fingerprint of what each part was last built from, so a build only
touches the parts whose inputs changed.
"""
