from utils.query_context import parse_query_context


def test_preview_only_query_does_not_start_auto_search():
    context = parse_query_context(
        {
            "query": "清华大学苏世民书院",
            "auto_search": "true",
            "preview_only": "true",
        }
    )

    assert context.query == "清华大学苏世民书院"
    assert context.auto_search is True
    assert context.preview_only is True
    assert context.should_start_research is False


def test_auto_search_query_starts_when_not_preview_only():
    context = parse_query_context(
        {
            "query": "清华大学苏世民书院",
            "auto_search": "true",
        }
    )

    assert context.should_start_research is True


def test_legacy_streamlit_query_params_are_supported():
    context = parse_query_context(
        {
            "query": ["清华大学苏世民书院"],
            "auto_search": ["false"],
            "preview_only": ["true"],
        }
    )

    assert context.query == "清华大学苏世民书院"
    assert context.auto_search is False
    assert context.preview_only is True
    assert context.should_start_research is False
