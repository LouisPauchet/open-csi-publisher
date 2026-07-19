from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
from pydantic import ValidationError

from open_csi_publisher.cli.matching import (
    detect_extra_dimension_groups,
    detect_gps_columns,
    detect_old_name_matches,
    load_known_variables,
    suggest_standard_name,
)
from open_csi_publisher.core.config_schema import DatasetConfig
from open_csi_publisher.providers.config.folder import (
    DatasetConfigNotFoundError,
    FolderConfigProvider,
)
from open_csi_publisher.providers.data.loggernet.toa5 import parse_toa5_header

_IGNORED_COLUMNS = {"TIMESTAMP", "RECORD"}


def build_config_dict(answers: dict[str, Any]) -> dict[str, Any]:
    """Assemble a full DatasetConfig-shaped dict from a flat answers
    structure — the one part of the CLI that's a pure function, independent
    of whether the answers came from prompts or a --answers JSON file."""
    return {
        "id": answers["id"],
        "source_type": answers.get("source_type", "loggernet"),
        "access": answers.get("access", "public"),
        "source_config": {
            "file_pattern": answers["file_pattern"],
            "timestamp_column": answers.get("timestamp_column", "TIMESTAMP"),
            "table_name": answers.get("table_name"),
        },
        "variables": answers["variables"],
        "platform_type": answers.get("platform_type", "fixed"),
        "deployments": answers["deployments"],
        "metadata": answers["metadata"],
        "output": {
            "file_naming": answers.get("file_naming", "{station}_{table}_{yyyy}-{mm}.nc"),
            "publish": answers.get("publish", False),
        },
    }


@click.command()
@click.option(
    "--data-root",
    type=click.Path(path_type=Path),
    default=Path("."),
    help="Root directory containing raw station files (interactive mode: used for file-pattern discovery and header scanning).",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=Path("."),
    help="Directory to write the new <id>.json config into.",
)
@click.option(
    "--answers",
    "answers_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="JSON file with pre-decided answers, for non-interactive/scripted config creation.",
)
@click.option("--force", is_flag=True, help="Overwrite an existing config for this dataset id.")
def main(data_root: Path, output_dir: Path, answers_path: Path | None, force: bool) -> None:
    """Create (or update) a dataset config, interactively or from --answers.

    Runs on the data-collection server (has mount write access) — separate
    from the read-only app server this package also contains, per
    implementation_plan.md §15.
    """
    if answers_path is not None:
        answers = json.loads(answers_path.read_text(encoding="utf-8"))
    else:
        answers = _run_interactive_flow(data_root)

    config_dict = build_config_dict(answers)
    try:
        config = DatasetConfig.model_validate(config_dict)
    except ValidationError as exc:
        click.echo(f"Config validation failed:\n{exc}", err=True)
        raise SystemExit(1) from exc

    output_path = output_dir / f"{config.id}.json"
    if output_path.exists() and not force:
        click.echo(f"{output_path} already exists (use --force to overwrite)", err=True)
        raise SystemExit(1)

    output_path.write_text(json.dumps(config_dict, indent=2) + "\n", encoding="utf-8")
    click.echo(f"Wrote {output_path}")


def _run_interactive_flow(data_root: Path) -> dict[str, Any]:
    click.echo("=== UNIS Data Portal — dataset config creator ===")

    dataset_id = click.prompt("Dataset id (also the output filename)")
    existing_variables = _load_existing_variables(data_root, dataset_id)

    file_pattern = _prompt_file_pattern(data_root)
    header = parse_toa5_header(data_root / file_pattern)
    raw_columns = [c for c in header.column_names if c not in _IGNORED_COLUMNS]

    if existing_variables:
        click.echo("\nExisting config found — comparing scanned columns against it:")
        classifications = detect_old_name_matches(raw_columns, existing_variables)
        for col, status in classifications.items():
            click.echo(f"  {col}: {status}")

    known_variables = load_known_variables()
    gps_columns = detect_gps_columns(raw_columns)
    platform_type = "fixed"
    if gps_columns and click.confirm(
        f"\nDetected likely GPS columns {list(gps_columns)} — is this a mobile platform?"
    ):
        platform_type = "mobile"

    extra_dimension_groups = detect_extra_dimension_groups(raw_columns)
    grouped_raw_names: set[str] = set()
    variables: list[dict[str, Any]] = []
    for group in extra_dimension_groups:
        member_names = [m["raw_name"] for m in group["members"]]
        if click.confirm(f"\nCombine {member_names} into one extra_dimension variable?"):
            standard_name = click.prompt("  standard_name for the combined variable")
            variables.append(
                {
                    "extra_dimension": {"name": "level", "units": group["dimension_units"]},
                    "members": group["members"],
                    "standard_name": standard_name,
                }
            )
            grouped_raw_names.update(member_names)

    for col in raw_columns:
        if col in grouped_raw_names:
            continue
        if col in gps_columns:
            variables.append({"raw_name": col, "standard_name": gps_columns[col]})
            continue
        suggestion = suggest_standard_name(col, known_variables)
        if suggestion and click.confirm(
            f"\nMap '{col}' -> standard_name '{suggestion['standard_name']}'?", default=True
        ):
            variables.append(
                {"raw_name": col, "standard_name": suggestion["standard_name"], "units": suggestion.get("units")}
            )
        elif click.confirm(f"Include '{col}' as an unmapped (raw-name-only) variable?", default=False):
            variables.append({"raw_name": col})
        # else: leave unmapped, dropped from the config entirely

    if platform_type == "fixed":
        start = click.prompt("Deployment start (ISO datetime)", default="2020-01-01T00:00:00Z")
        lat = click.prompt("Latitude", type=float)
        lon = click.prompt("Longitude", type=float)
        deployments = [{"start": start, "end": None, "lat": lat, "lon": lon}]
    else:
        start = click.prompt("Deployment start (ISO datetime)")
        platform_name = click.prompt("Platform name (e.g. vessel name)")
        deployments = [{"start": start, "end": None, "platform_name": platform_name}]

    title = click.prompt("Dataset title")
    institution = click.prompt("Institution", default="University Centre in Svalbard (UNIS)")
    access = "restricted" if click.confirm("Restricted access?", default=False) else "public"

    return {
        "id": dataset_id,
        "file_pattern": file_pattern,
        "table_name": header.table_name,
        "variables": variables,
        "platform_type": platform_type,
        "deployments": deployments,
        "metadata": {"title": title, "institution": institution},
        "access": access,
    }


def _prompt_file_pattern(data_root: Path) -> str:
    while True:
        pattern = click.prompt("Live file path/pattern (relative to data root), ending in .dat")
        matches = sorted(data_root.glob(pattern))
        if len(matches) == 1:
            click.echo(f"Matched: {matches[0].relative_to(data_root)}")
            return str(matches[0].relative_to(data_root)).replace("\\", "/")
        if not matches:
            click.echo("No files matched — try again.")
        else:
            click.echo(f"{len(matches)} files matched, need exactly one — refine the pattern.")


def _load_existing_variables(data_root: Path, dataset_id: str):
    try:
        provider = FolderConfigProvider(data_root)
        existing = DatasetConfig.model_validate(provider.load_config(dataset_id))
        return existing.variables
    except (DatasetConfigNotFoundError, FileNotFoundError, ValidationError):
        return None


if __name__ == "__main__":
    main()
