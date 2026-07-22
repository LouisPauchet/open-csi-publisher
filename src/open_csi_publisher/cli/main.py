from __future__ import annotations

from pathlib import Path

import click

from open_csi_publisher.cli.validate import validate_loggernet_configs


@click.group()
def cli() -> None:
    """open-csi-publisher-cli: operational tooling for the data portal."""


@cli.group()
def validate() -> None:
    """Validate on-disk configuration."""


@validate.command("loggernet")
@click.argument("config_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--data-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Also validate the TOA5 headers of each config's matched files under this root.",
)
def validate_loggernet(config_dir: Path, data_root: Path | None) -> None:
    """Validate every *.json config in CONFIG_DIR as a loggernet dataset config,
    logging exactly what is wrong with each invalid one."""
    results = validate_loggernet_configs(config_dir, data_root=data_root)

    for result in results:
        if result.status == "valid":
            click.echo(f"OK      {result.path}")
        elif result.status == "skipped":
            click.echo(f"SKIPPED {result.path}: {result.messages[0]}")
        else:
            click.echo(f"INVALID {result.path}")
            for message in result.messages:
                for line in message.splitlines():
                    click.echo(f"        {line}")

    n_valid = sum(1 for r in results if r.status == "valid")
    n_invalid = sum(1 for r in results if r.status == "invalid")
    n_skipped = sum(1 for r in results if r.status == "skipped")
    click.echo(f"\n{n_valid} valid, {n_invalid} invalid, {n_skipped} skipped")

    if n_invalid:
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
