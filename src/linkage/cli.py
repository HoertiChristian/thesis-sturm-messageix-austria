"""Command-line interface — the ``sturm-messageix`` entry point.

Registered in ``pyproject.toml`` as ``sturm-messageix = "linkage.cli:cli"``.
A thin wrapper over :mod:`linkage.pipeline`; configuration is read via
:meth:`Config.load` (the ``config`` sheet of ``data/inputs.xlsx``).
"""

from __future__ import annotations

import logging

import click

from common import __version__
from common.config import Config
from common.scenarios import digitalization_levels, matrix, pathways
from linkage.pipeline import run_scenarios
from linkage.runlog import start as start_runlog


@click.group()
@click.version_option(__version__)
def cli() -> None:
    """STURM ⇄ MESSAGEix-Austria soft-linkage."""
    logging.basicConfig(level=logging.INFO)


@cli.command(name="list")
def list_scenarios() -> None:
    """List the nine scenarios of the matrix."""
    for scenario in matrix():
        click.echo(scenario.id)


@cli.command()
@click.option(
    "--pathway",
    "pathway_id",
    type=click.Choice(sorted(pathways())),
    help="Run a single pathway; omit to run all.",
)
@click.option(
    "--digitalization",
    "digi_id",
    type=click.Choice(sorted(digitalization_levels())),
    help="Run a single digitalization level; omit to run all.",
)
def run(pathway_id: str | None, digi_id: str | None) -> None:
    """Build, link and solve scenarios (options from ``data/inputs.xlsx``)."""
    config = Config.load()
    logfile = start_runlog()  # results/logs/run_<UTC>.log — read by viz/convergence_table.py
    click.echo(f"run log -> {logfile}")
    selected = [
        s
        for s in matrix()
        if (pathway_id is None or s.pathway.id == pathway_id)
        and (digi_id is None or s.digitalization.id == digi_id)
    ]
    # One shared platform for the whole batch (opening a fresh platform per cell can
    # corrupt the ixmp HSQLDB store mid-run; see run_scenarios).
    run_scenarios(selected, config)


if __name__ == "__main__":
    cli()
