def test_source_start_allows_werkzeug_dev_server(monkeypatch):
    import app

    calls = {}

    def fake_run(flask_app, **kwargs):
        calls["flask_app"] = flask_app
        calls.update(kwargs)

    monkeypatch.setattr(app.socketio, "run", fake_run)

    app.run_flask_server()

    assert calls["flask_app"] is app.app
    assert calls["debug"] is False
    assert calls["allow_unsafe_werkzeug"] is True


def test_settings_exposes_flask_secret_key_from_environment(monkeypatch):
    from config import Settings

    monkeypatch.setenv("SECRET_KEY", "team-shared-dev-secret")

    assert Settings(_env_file=None).SECRET_KEY == "team-shared-dev-secret"


def test_settings_ignores_blank_flask_secret_key():
    from config import Settings

    assert Settings(_env_file=None, SECRET_KEY="").SECRET_KEY == "bettafish-local-dev-secret"


def test_env_example_does_not_blank_flask_secret_key():
    from config import Settings

    assert Settings(_env_file=".env.example").SECRET_KEY == "bettafish-local-dev-secret"


def test_flask_secret_key_comes_from_settings():
    import app

    assert app.app.config["SECRET_KEY"] == app.settings.SECRET_KEY
    assert (
        app.app.config["SECRET_KEY"]
        != "Dedicated-to-creating-a-concise-and-versatile-public-opinion-analysis-platform"
    )
