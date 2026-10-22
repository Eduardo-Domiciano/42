from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "data"
PROFILES_PATH = ROOT / "source_profiles.yml"

_DEFAULT_CORS = (
    "http://localhost:4200,http://127.0.0.1:4200,"
    "http://localhost:8080,http://127.0.0.1:8080"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "④②"
    database_url: str = f"sqlite:///{DEFAULT_DATA_DIR / 'veracidade.db'}"
    # String (não list): pydantic-settings tenta JSON em list[str] e quebra com CSV do Docker
    cors_origins: str = Field(default=_DEFAULT_CORS)
    topic_search_max_results: int = 12
    # Poucos fetches: DDG + sites BR demoram; nginx/proxy estourava em 120s.
    topic_search_web_candidates: int = 14
    topic_min_relevance: float = 0.32
    topic_min_semantic: float = 0.48
    topic_min_lexical_for_semantic: float = 0.28
    topic_require_published_at_in_range: bool = True
    http_timeout_seconds: float = 18.0
    # ASCII only: httpx/headers rejeitam caracteres como ④②
    user_agent: str = (
        "Mozilla/5.0 (compatible; Projeto42/0.1; +local; pesquisa educacional)"
    )

    # F3 — claims / LLM
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    claim_use_llm: bool = True
    claim_max_per_article: int = 5
    claim_llm_max_per_topic: int = 3
    llm_timeout_seconds: float = 60.0

    # F4 — cruzamento
    crossref_enabled: bool = True
    crossref_max_peers: int = 6
    crossref_window_days: int = 14
    crossref_min_local_before_web: int = 2
    crossref_use_llm_stance: bool = False
    crossref_max_claims_url: int = 3
    crossref_on_topic: bool = True

    # Redes neurais locais (complemento; fallback automático se pacotes/modelos falharem)
    nn_enabled: bool = True
    nn_nli_enabled: bool = True
    nn_embeddings_enabled: bool = True
    nn_clickbait_enabled: bool = True
    nn_nli_model: str = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
    nn_embed_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    nn_peer_pool_multiplier: int = 3

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origin_list(self) -> list[str]:
        return [part.strip() for part in self.cors_origins.split(",") if part.strip()]


settings = Settings()

if settings.database_url.startswith("sqlite:///"):
    db_path = Path(settings.database_url.removeprefix("sqlite:///"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
else:
    DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
