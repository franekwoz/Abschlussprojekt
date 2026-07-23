"""Flask-Anwendung fuer die E-Bike-Routensimulation."""
from flask import Flask
from pathlib import Path


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    root = Path(__file__).resolve().parents[1]
    app.config.from_mapping(
        SECRET_KEY="development-key-change-me",
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
        PROJECT_ROOT=root,
        WEB_OUTPUT=root / "output" / "web",
    )
    if test_config:
        app.config.update(test_config)
    app.config["WEB_OUTPUT"].mkdir(parents=True, exist_ok=True)
    from .routes import bp
    app.register_blueprint(bp)
    return app
