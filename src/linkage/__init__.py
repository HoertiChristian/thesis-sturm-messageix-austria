"""The STURM ⇄ MESSAGEix-Austria soft-linkage — the project's contribution.

The iterative driver (:func:`linkage.loop.run`) runs, each iteration: STURM →
final energy by fuel → **activity bounds** on the end-use conversion
technologies (:mod:`linkage.bounds`) → solve → read commodity prices → feed
back to STURM, repeating until the activity-bound vector converges
(:mod:`linkage.convergence`). STURM dictates the buildings fuel mix; MESSAGEix
resolves the rest of the system.

Also home of the orchestration front-ends: :mod:`linkage.pipeline` (per-cell
runs, reports, ``*.meta.json`` sidecars) and :mod:`linkage.cli` (the
``sturm-messageix`` entry point).
"""
