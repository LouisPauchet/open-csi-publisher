from __future__ import annotations

from open_csi_publisher.settings import Settings


def test_defaults_require_no_environment_variables(monkeypatch):
    for var in (
        "DATABASE_URL",
        "SOURCES_FILE",
        "OIDC_ISSUER",
        "OIDC_CLIENT_ID",
        "OIDC_CLIENT_SECRET",
        "SESSION_SECRET_KEY",
    ):
        monkeypatch.delenv(var, raising=False)

    settings = Settings()
    assert settings.database_url == "sqlite:///./local/state.db"
    assert settings.sources_file == "sample_configs/sources.yaml"
    assert settings.branding_file == "sample_configs/branding.yaml"
    assert settings.oidc_issuer is None
    assert settings.oidc_client_id is None
    assert settings.oidc_client_secret is None
    assert settings.session_secret_key is None


def test_database_url_overridable_via_env_var(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    assert Settings().database_url == "postgresql://example/db"


def test_oidc_issuer_overridable_via_env_var(monkeypatch):
    monkeypatch.setenv("OIDC_ISSUER", "https://login.microsoftonline.com/tenant-id/v2.0")
    assert Settings().oidc_issuer == "https://login.microsoftonline.com/tenant-id/v2.0"


def test_publish_api_keys_defaults_to_empty_list(monkeypatch):
    monkeypatch.delenv("PUBLISH_API_KEYS_RAW", raising=False)
    assert Settings().publish_api_keys == []


def test_publish_api_keys_parses_comma_separated_env_var(monkeypatch):
    monkeypatch.setenv("PUBLISH_API_KEYS_RAW", "key-one, key-two,key-three")
    assert Settings().publish_api_keys == ["key-one", "key-two", "key-three"]


def test_publish_api_keys_drops_empty_entries(monkeypatch):
    monkeypatch.setenv("PUBLISH_API_KEYS_RAW", "key-one,, ,key-two")
    assert Settings().publish_api_keys == ["key-one", "key-two"]


def test_publish_cache_dir_default(monkeypatch):
    monkeypatch.delenv("PUBLISH_CACHE_DIR", raising=False)
    assert Settings().publish_cache_dir == "local/publish_cache"
