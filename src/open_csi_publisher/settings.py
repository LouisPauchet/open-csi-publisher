from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./local/state.db"
    sources_file: str = "sample_configs/sources.yaml"
    branding_file: str = "sample_configs/branding.yaml"
    base_dir: str = "."

    # Auth seam (implementation_plan.md §10): unset by default, meaning every
    # caller is anonymous (api/auth.py::get_current_user always returns None) and
    # restricted datasets stay hidden, until real Entra ID/OIDC values are
    # supplied via environment variables. The OIDC callback flow itself isn't
    # built yet — these fields exist now so wiring it in later doesn't require a
    # settings/schema change.
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    session_secret_key: str | None = None

    # Publish endpoint (implementation_plan.md §11): a separate, simpler
    # static-API-key mechanism, not the OIDC session flow above — a small
    # number of trusted server-to-server consumers (the data center), not
    # end users. Comma-separated since env vars can't carry a native list.
    publish_api_keys_raw: str = ""
    publish_cache_dir: str = "local/publish_cache"

    @property
    def publish_api_keys(self) -> list[str]:
        return [key.strip() for key in self.publish_api_keys_raw.split(",") if key.strip()]

    # ThingsBoard: a tenant's own base_url/username/password are NOT settings
    # fields — sources.py::_get_thingsboard_client() reads them straight from
    # the environment, keyed by each SourceEntry's own credentials_env_prefix,
    # since the set of valid prefixes is open-ended (one per configured
    # thingsboard source, potentially many). This interval is the one
    # ThingsBoard-related value that IS shared/global across every instance —
    # an operational tuning knob, not a secret.
    thingsboard_discovery_interval_seconds: int = 3600


settings = Settings()
