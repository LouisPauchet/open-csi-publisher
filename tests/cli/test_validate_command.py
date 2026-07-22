from __future__ import annotations

import json

from click.testing import CliRunner

from open_csi_publisher.cli.main import cli

VALID_LOGGERNET_CONFIG = {
    "id": "test_station",
    "source_type": "loggernet",
    "access": "public",
    "source_config": {"file_pattern": "test_station/Test_Table.dat"},
    "variables": [{"raw_name": "AirT_C", "standard_name": "air_temperature", "units": "degC"}],
    "platform_type": "fixed",
    "deployments": [{"start": "2020-01-01T00:00:00Z", "end": None, "lat": 78.0, "lon": 13.6}],
    "metadata": {"title": "Test Station"},
    "output": {"file_naming": "{station}_{table}_{yyyy}-{mm}.nc"},
}

GENERIC_CSV_CONFIG = {
    "id": "csv_station",
    "source_type": "generic_csv",
    "access": "public",
    "source_config": {"file_path": "csv_station/data.csv"},
    "variables": [{"raw_name": "AirT_C", "standard_name": "air_temperature"}],
    "platform_type": "fixed",
    "deployments": [{"start": "2020-01-01T00:00:00Z", "end": None, "lat": 78.0, "lon": 13.6}],
    "metadata": {"title": "CSV Station"},
    "output": {"file_naming": "{station}_{table}_{yyyy}-{mm}.nc"},
}


def _write(path, doc) -> None:
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_validate_loggernet_all_valid_exits_zero(tmp_path):
    _write(tmp_path / "test_station.json", VALID_LOGGERNET_CONFIG)

    result = CliRunner().invoke(cli, ["validate", "loggernet", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "OK" in result.output
    assert "1 valid, 0 invalid, 0 skipped" in result.output


def test_validate_loggernet_schema_invalid_config_reported_with_path_and_error(tmp_path):
    bad = dict(VALID_LOGGERNET_CONFIG)
    bad["platform_type"] = "mobile"  # missing lat/lon-forbidden + missing GPS vars
    config_path = tmp_path / "test_station.json"
    _write(config_path, bad)

    result = CliRunner().invoke(cli, ["validate", "loggernet", str(tmp_path)])

    assert result.exit_code != 0
    assert "INVALID" in result.output
    assert str(config_path) in result.output


def test_validate_loggernet_non_json_file_reported_with_path(tmp_path):
    bad_path = tmp_path / "broken.json"
    bad_path.write_text("{not valid json", encoding="utf-8")

    result = CliRunner().invoke(cli, ["validate", "loggernet", str(tmp_path)])

    assert result.exit_code != 0
    assert "INVALID" in result.output
    assert str(bad_path) in result.output


def test_validate_loggernet_non_loggernet_config_is_skipped_not_fatal(tmp_path):
    _write(tmp_path / "csv_station.json", GENERIC_CSV_CONFIG)

    result = CliRunner().invoke(cli, ["validate", "loggernet", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "SKIPPED" in result.output
    assert "0 valid, 0 invalid, 1 skipped" in result.output


def test_validate_loggernet_data_root_reports_non_toa5_matched_file(tmp_path):
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    data_root = tmp_path / "data"
    (data_root / "test_station").mkdir(parents=True)

    _write(config_dir / "test_station.json", VALID_LOGGERNET_CONFIG)
    (data_root / "test_station" / "Test_Table.dat").write_text(
        "not,a,toa5,header\n1,2,3,4\n", encoding="utf-8"
    )

    result = CliRunner().invoke(
        cli, ["validate", "loggernet", str(config_dir), "--data-root", str(data_root)]
    )

    assert result.exit_code != 0
    assert "INVALID" in result.output
    assert "0 valid, 1 invalid, 0 skipped" in result.output


def test_validate_loggernet_data_root_accepts_a_real_toa5_file(tmp_path):
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    data_root = tmp_path / "data"
    (data_root / "test_station").mkdir(parents=True)

    _write(config_dir / "test_station.json", VALID_LOGGERNET_CONFIG)
    (data_root / "test_station" / "Test_Table.dat").write_text(
        '"TOA5","Station","CR1000","12345","CR1000.Std.01","Program.CR1","1234","Table"\n'
        '"TIMESTAMP","RECORD","AirT_C"\n'
        '"TS","RN","Deg C"\n'
        '"","Smp","Avg"\n'
        '"2026-01-01 00:00:00",0,1.0\n',
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        cli, ["validate", "loggernet", str(config_dir), "--data-root", str(data_root)]
    )

    assert result.exit_code == 0, result.output
    assert "1 valid, 0 invalid, 0 skipped" in result.output
