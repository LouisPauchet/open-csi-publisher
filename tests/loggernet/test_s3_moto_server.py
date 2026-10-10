"""End-to-end against a real S3 HTTP endpoint (moto server): exercises the env vars,
endpoint, path-style addressing and read-only guarantee through make_storage."""

from __future__ import annotations

import boto3
import pytest
from moto.server import ThreadedMotoServer

from open_csi_publisher.core.config_schema import LoggerNetSourceConfig
from open_csi_publisher.sources import SourceEntry, get_config_provider, get_data_provider

from .test_s3_storage import HISTORICAL, LIVE

CONFIG_JSON = (
    '{"id":"d","source_type":"loggernet","access":"public",'
    '"source_config":{"file_pattern":"st/Station_Table.dat"},'
    '"variables":[{"raw_name":"AirT_C","standard_name":"air_temperature"}],'
    '"platform_type":"fixed",'
    '"deployments":[{"start":"2020-01-01T00:00:00Z","end":null,"lat":78.0,"lon":13.6}],'
    '"metadata":{"title":"D"},"output":{"file_naming":"{station}.nc"}}'
)


@pytest.fixture(scope="module")
def endpoint():
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=0)
    server.start()
    _, port = server.get_host_and_port()
    yield f"http://127.0.0.1:{port}"
    server.stop()


@pytest.fixture
def bucket(endpoint, monkeypatch):
    client = boto3.client(
        "s3", endpoint_url=endpoint, region_name="us-east-1",
        aws_access_key_id="k", aws_secret_access_key="s",
    )
    client.create_bucket(Bucket="ofs")
    client.put_object(Bucket="ofs", Key="__config__/d.json", Body=CONFIG_JSON.encode())
    client.put_object(Bucket="ofs", Key="st/Station_Table.dat", Body=LIVE.encode())
    client.put_object(Bucket="ofs", Key="st/Station_Table_Historical.dat", Body=HISTORICAL.encode())
    for k, v in {"ACCESS_KEY_ID": "k", "SECRET_ACCESS_KEY": "s", "ENDPOINT": endpoint,
                 "REGION": "us-east-1", "BUCKET": "ofs"}.items():
        monkeypatch.setenv(f"LN_OFS_S3_{k}", v)
    yield client
    for obj in client.list_objects_v2(Bucket="ofs").get("Contents", []):
        client.delete_object(Bucket="ofs", Key=obj["Key"])
    client.delete_bucket(Bucket="ofs")


def _etags(client):
    return {o["Key"]: o["ETag"] for o in client.list_objects_v2(Bucket="ofs")["Contents"]}


def test_sources_yaml_style_entry_reads_from_s3_and_never_writes(bucket, tmp_path):
    source = SourceEntry(
        id="loggernet_ofs", type="loggernet", config_provider="folder",
        config_location="s3:///__config__/", data_location="s3:///",
        credentials_env_prefix="LN_OFS_S3",
    )
    before = _etags(bucket)

    config_provider = get_config_provider(source, base_dir=tmp_path)
    assert config_provider.list_dataset_ids() == ["d"]
    assert config_provider.load_config("d")["id"] == "d"

    data_provider = get_data_provider(source, base_dir=tmp_path)
    cfg = LoggerNetSourceConfig(file_pattern="st/Station_Table.dat")
    records = data_provider.get_file_index(cfg)
    ds = data_provider.read_range(cfg, records, None, None)

    assert ds["AirT_C"].values.tolist() == [0.5, 1.0, 2.0, 3.0]
    assert _etags(bucket) == before
