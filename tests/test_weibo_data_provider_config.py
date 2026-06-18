from config import Settings
from utils.weibo_data_prep import build_weibo_data_caps, select_weibo_provider


def test_default_provider_is_tikhub_for_mvp():
    settings = Settings(_env_file=None)

    provider = select_weibo_provider(settings)

    assert settings.WEIBO_DATA_PROVIDER == "tikhub"
    assert provider.name == "tikhub"


def test_explicit_mediacrawler_provider_still_supported():
    settings = Settings(_env_file=None, WEIBO_DATA_PROVIDER="mediacrawler")

    provider = select_weibo_provider(settings)

    assert provider.name == "mediacrawler"


def test_tikhub_provider_uses_env_settings():
    settings = Settings(
        _env_file=None,
        WEIBO_DATA_PROVIDER="tikhub",
        TIKHUB_BASE_URL="http://127.0.0.1:8317/v1",
        TIKHUB_API_KEY="sk-test",
        TIKHUB_TIMEOUT=7,
        WEIBO_DATA_SEARCH_PAGES_PER_KEYWORD=1,
        WEIBO_DATA_SEARCH_TYPE="1",
    )

    provider = select_weibo_provider(settings)

    assert provider.name == "tikhub"
    assert provider.base_url == "http://127.0.0.1:8317/v1"
    assert provider.api_key == "sk-test"
    assert provider.timeout == 7
    assert provider.pages_per_keyword == 1
    assert provider.search_type == "1"


def test_weibo_data_caps_use_mvp_defaults():
    settings = Settings(_env_file=None)

    caps = build_weibo_data_caps(settings)

    assert caps.to_dict() == {
        "max_keywords": 6,
        "max_posts_per_keyword": 30,
        "max_selected_posts": 12,
        "max_comments_per_post": 20,
        "max_comments_per_post_hard": 30,
        "allow_subcomments": False,
    }


def test_weibo_data_caps_hard_disable_subcomments_even_if_configured():
    settings = Settings(_env_file=None, WEIBO_DATA_ALLOW_SUBCOMMENTS=True)

    caps = build_weibo_data_caps(settings)

    assert caps.allow_subcomments is False
