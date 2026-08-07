from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./local/state.db"
    sources_file: str = "sample_configs/sources.yaml"
    branding_file: str = "sample_configs/branding.yaml"
    base_dir: str = "."

    # Set when this app is deployed behind a reverse proxy on a subpath (e.g.
    # https://host/csi-publisher/ instead of the domain root) — passed straight
    # through to FastAPI(root_path=...) (api/app.py::create_app), which is the
    # documented mechanism for exactly this "can't control the uvicorn/proxy
    # startup command" scenario. Every outbound URL this app builds (templates,
    # static JS, auth redirects, the publish endpoint's JSON contract) is
    # prefixed with this value. The proxy itself must strip the prefix before
    # forwarding to this app — that's the operator's own proxy config, not
    # something this app does. Trailing slashes are normalized away so
    # "/csi-publisher/" and "/csi-publisher" behave identically, and "/" (no
    # real prefix) normalizes to "", matching FastAPI's own "unset" convention.
    root_path: str = ""

    @field_validator("root_path")
    @classmethod
    def _normalize_root_path(cls, value: str) -> str:
        return value.rstrip("/")

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

    @property
    def oidc_configured(self) -> bool:
        """True only when every field the OIDC login flow needs is set. A partially
        configured OIDC setup (e.g. `oidc_issuer` set but `session_secret_key`
        missing) is treated the same as entirely unset — login is disabled, not a
        startup crash — so every caller of this property is the single place that
        decides "is login on", instead of each one separately checking
        `oidc_issuer is not None`.
        """
        return bool(
            self.oidc_issuer
            and self.oidc_client_id
            and self.oidc_client_secret
            and self.session_secret_key
        )

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

    # How long a dataset's config-hash check (which for ThingsBoard-backed
    # sources costs 2 HTTP calls) is trusted before being re-verified against
    # the source on the next access (core/config_versioning.py). Within this
    # window, get_versioned_config() serves the already-snapshotted content
    # without contacting the source at all — station metadata is no longer
    # rechecked on every single reload.
    config_recheck_interval_seconds: float = 300

    # Redis-backed cache of parsed LoggerNet/generic-CSV file content
    # (providers/data/loggernet/provider.py, providers/data/generic_csv/provider.py)
    # — unset (the default) disables caching entirely, same "None means off"
    # convention as oidc_issuer. TOA5 parsing can be slow for large
    # files, so an archived (closed, immutable) file is cached far longer
    # than a still-being-appended-to live one.
    redis_url: str | None = None
    redis_cache_ttl_seconds: int = 300
    redis_archived_cache_ttl_seconds: int = 2_592_000


settings = Settings()
