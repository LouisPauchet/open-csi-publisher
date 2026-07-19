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
