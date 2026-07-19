from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./local/state.db"
    sources_file: str = "sample_configs/sources.yaml"
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


settings = Settings()
