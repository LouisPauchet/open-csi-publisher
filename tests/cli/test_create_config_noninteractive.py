from __future__ import annotations

import json

from click.testing import CliRunner

from open_csi_publisher.cli.create_config import build_config_dict, main
from open_csi_publisher.core.config_schema import DatasetConfig

VALID_ANSWERS = {
    "id": "test_station",
    "file_pattern": "test_station/Test_Table.dat",
    "table_name": "Test_Table",
    "variables": [
        {"raw_name": "AirT_C", "standard_name": "air_temperature", "units": "degC"},
        {"raw_name": "MetSENS_Status", "dtype": "string"},
    ],
    "platform_type": "fixed",
    "deployments": [{"start": "2020-01-01T00:00:00Z", "end": None, "lat": 78.0, "lon": 13.6}],
    "metadata": {"title": "Test Station", "institution": "UNIS"},
    "access": "public",
}


def test_build_config_dict_produces_a_valid_dataset_config():
    config_dict = build_config_dict(VALID_ANSWERS)
    config = DatasetConfig.model_validate(config_dict)
    assert config.id == "test_station"
    assert config.source_config.file_pattern == "test_station/Test_Table.dat"
    assert config.access == "public"


def test_build_config_dict_defaults():
    minimal = {
        "id": "x",
        "file_pattern": "x/Table.dat",
        "variables": [{"raw_name": "a", "standard_name": "air_temperature"}],
        "deployments": [{"start": "2020-01-01T00:00:00Z", "end": None, "lat": 1.0, "lon": 2.0}],
        "metadata": {"title": "X"},
    }
    config_dict = build_config_dict(minimal)
    config = DatasetConfig.model_validate(config_dict)
    assert config.platform_type == "fixed"
    assert config.access == "public"
    assert config.output.publish is False
    assert config.source_config.timestamp_column == "TIMESTAMP"


def test_cli_noninteractive_run_writes_a_valid_config(tmp_path):
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps(VALID_ANSWERS), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        main, ["--answers", str(answers_path), "--output-dir", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output
    written = tmp_path / "test_station.json"
    assert written.is_file()
    config = DatasetConfig.model_validate(json.loads(written.read_text(encoding="utf-8")))
    assert config.id == "test_station"


def test_cli_noninteractive_run_reports_validation_errors_clearly(tmp_path):
    bad_answers = dict(VALID_ANSWERS)
    bad_answers["platform_type"] = "mobile"  # missing lat/lon-forbidden + missing GPS vars
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps(bad_answers), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        main, ["--answers", str(answers_path), "--output-dir", str(tmp_path)]
    )

    assert result.exit_code != 0
    assert not (tmp_path / "test_station.json").exists()


def test_cli_noninteractive_run_does_not_overwrite_without_force(tmp_path):
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps(VALID_ANSWERS), encoding="utf-8")
    existing = tmp_path / "test_station.json"
    existing.write_text('{"already": "here"}', encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        main, ["--answers", str(answers_path), "--output-dir", str(tmp_path)]
    )

    assert result.exit_code != 0
    assert json.loads(existing.read_text(encoding="utf-8")) == {"already": "here"}


def test_cli_noninteractive_run_overwrites_with_force(tmp_path):
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps(VALID_ANSWERS), encoding="utf-8")
    existing = tmp_path / "test_station.json"
    existing.write_text('{"already": "here"}', encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        main, ["--answers", str(answers_path), "--output-dir", str(tmp_path), "--force"]
    )

    assert result.exit_code == 0, result.output
    config = DatasetConfig.model_validate(json.loads(existing.read_text(encoding="utf-8")))
    assert config.id == "test_station"
