"""Точка входу застосунку LOQ Market: конфігурація Flask, ініціалізація БД та реєстрація Blueprint."""
import os
from pathlib import Path

from flasgger import Swagger
from flask import Flask, abort, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.exceptions import HTTPException

import models
import seed_data
from routes import admin_bp, api_bp, auth_bp, feedback_bp, shop_bp
from routes.api import SWAGGER_CONFIG, SWAGGER_TEMPLATE

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("LOQ_MARKET_SECRET_KEY", "loq-market-development-key")
app.json.ensure_ascii = False
app.json.sort_keys = False
Path(app.instance_path).mkdir(parents=True, exist_ok=True)
app.config["DATABASE"] = os.environ.get("DATABASE", str(Path(app.instance_path) / "loq_market.sqlite3"))

models.init_app(app)

with app.app_context():
    models.init_db()
    seed_data.seed()

app.register_blueprint(auth_bp)
app.register_blueprint(feedback_bp)
app.register_blueprint(shop_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(api_bp)

swagger = Swagger(app, config=SWAGGER_CONFIG, template=SWAGGER_TEMPLATE)


API_ERROR_MESSAGES = {
    400: "Некоректний запит",
    401: "Потрібна автентифікація",
    403: "Доступ заборонено",
    404: "Ресурс не знайдено",
    405: "Метод не дозволений для цієї адреси",
    409: "Конфлікт даних під час виконання запиту",
    415: "Непідтримуваний тип даних (очікується application/json)",
    422: "Неможливо обробити передані дані",
    500: "Внутрішня помилка сервера",
    503: "Сервіс тимчасово недоступний",
}


def _is_api_request():
    return request.path == "/api" or request.path.startswith("/api/")


@app.errorhandler(HTTPException)
def handle_http_error(error):
    """Для адрес /api/... повертає JSON-помилку, для вебсторінок — стандартну відповідь."""
    if _is_api_request():
        status = error.code or 500
        message = API_ERROR_MESSAGES.get(status, error.description or "Помилка запиту")
        return jsonify({"error": message}), status
    return error


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    """Перехоплює непередбачені помилки на /api/... і повертає JSON зі статусом 500."""
    if _is_api_request():
        app.logger.exception("Непередбачена помилка API", exc_info=error)
        return jsonify({"error": API_ERROR_MESSAGES[500]}), 500
    raise error


@app.before_request
def load_current_user_and_protect_admin():
    user_id = session.get("user_id")
    g.current_user = models.get_user(user_id) if user_id else None
    if user_id and g.current_user is None:
        session.clear()

    endpoint = request.endpoint or ""
    if endpoint.startswith("admin."):
        if not models.has_admin():
            return redirect(url_for("auth.setup_admin"))
        if g.current_user is None:
            return redirect(url_for("auth.login", next=request.path))
        if g.current_user["role"] != "admin":
            abort(403)


@app.context_processor
def inject_user_navigation():
    return {
        "current_user": getattr(g, "current_user", None),
        "admin_setup_required": not models.has_admin(),
    }


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/about")
def about():
    return render_template("about.html")


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
