"""Спільні допоміжні функції валідації, пагінації та формування відповідей для REST API v1 і v2."""
from datetime import date
import math
import re
import sqlite3

from flask import current_app, jsonify, request

import models

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PROMO_RE = re.compile(r"^[A-Z0-9_-]{3,32}$")

API_ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    500: "INTERNAL_SERVER_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


def is_int(value):
    """Перевіряє, що значення є цілим числом, а не bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value):
    """Перевіряє, що значення є скінченним числом, а не bool."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def is_valid_email(value):
    """Перевіряє коректність формату email-адреси."""
    return isinstance(value, str) and len(value.strip()) <= 254 and bool(_EMAIL_RE.fullmatch(value.strip()))


def error_response(message, status):
    """Формує базову JSON-помилку (формат API v1)."""
    return jsonify({"error": message}), status


def v2_error_response(message, status, code=None, details=None):
    """Формує деталізовану JSON-помилку (формат API v2) із кодом помилки та деталями полів."""
    payload = {
        "error": message,
        "code": code or API_ERROR_CODES.get(status, "API_ERROR"),
        "status": status,
    }
    if details:
        payload["details"] = details
    return jsonify(payload), status


def register_db_error_handler(blueprint, v2=False):
    """Реєструє обробник помилок SQLite на переданому Blueprint."""

    @blueprint.errorhandler(sqlite3.Error)
    def handle_database_error(error):
        current_app.logger.exception("Помилка бази даних в API", exc_info=error)
        if v2:
            return v2_error_response("Помилка роботи з базою даних.", 500, "DATABASE_ERROR")
        return error_response("Помилка роботи з базою даних.", 500)


def parse_json_object(v2=False):
    """Читає JSON-об'єкт із тіла запиту та повертає (data, error_response)."""
    respond = v2_error_response if v2 else (lambda msg, st, _code=None: error_response(msg, st))
    if not request.is_json:
        status = 415 if v2 else 400
        return None, respond("Запит повинен мати заголовок Content-Type: application/json.", status, "UNSUPPORTED_MEDIA_TYPE")
    data = request.get_json(silent=True)
    if data is None:
        return None, respond("Некоректний JSON у тілі запиту.", 400, "INVALID_JSON")
    if not isinstance(data, dict):
        return None, respond("Тіло запиту має бути JSON-об'єктом.", 400, "INVALID_PAYLOAD")
    return data, None


def _validate_nonempty_str(value, max_len, label):
    if not isinstance(value, str) or not value.strip():
        return None, f"Поле {label} обов'язкове й має бути непорожнім рядком."
    cleaned = value.strip()
    if len(cleaned) > max_len:
        return None, f"Поле {label} не може перевищувати {max_len} символів."
    return cleaned, None


def validate_product_payload(data, partial=False, strict_url=False):
    """Валідує поля товару; при partial=True перевіряє лише передані ключі."""
    errors = {}
    parsed = {}

    if partial and not data:
        errors["_body"] = "Потрібно передати хоча б одне поле для оновлення."
        return None, errors

    for field in ("weapon", "skin", "quality"):
        if not partial or field in data:
            cleaned, err = _validate_nonempty_str(data.get(field), 100, field)
            if err:
                errors[field] = err
            else:
                parsed[field] = cleaned

    if not partial or "price" in data:
        price = data.get("price")
        if not is_number(price) or price < 0:
            errors["price"] = "Поле price обов'язкове й має бути числом не менше 0."
        else:
            parsed["price"] = round(float(price), 2)

    if not partial or "stock" in data:
        stock = data.get("stock", 10) if not partial else data.get("stock")
        if not is_int(stock) or stock < 0:
            errors["stock"] = "Поле stock має бути цілим невід'ємним числом."
        else:
            parsed["stock"] = stock

    if not partial or "image_url" in data:
        image_url = data.get("image_url", "") if not partial else data.get("image_url")
        if not isinstance(image_url, str):
            errors["image_url"] = "Поле image_url має бути рядком."
        else:
            cleaned_url = image_url.strip()
            if len(cleaned_url) > 1000:
                errors["image_url"] = "Поле image_url не може перевищувати 1000 символів."
            elif strict_url and cleaned_url and not cleaned_url.startswith(("http://", "https://", "/")):
                errors["image_url"] = "Поле image_url має починатися з http://, https:// або /."
            else:
                parsed["image_url"] = cleaned_url

    if not partial or "category_id" in data:
        category_id = data.get("category_id")
        if category_id is not None:
            if not is_int(category_id) or category_id < 1:
                errors["category_id"] = "Поле category_id має бути додатним цілим числом або null."
            else:
                category_ids = {category["id"] for category in models.get_categories()}
                if category_id not in category_ids:
                    errors["category_id"] = "Вказану категорію не знайдено."
                else:
                    parsed["category_id"] = category_id
        else:
            parsed["category_id"] = None

    return (None, errors) if errors else (parsed, {})


def validate_order_payload(data):
    """Валідує вхідні дані для створення замовлення."""
    errors = {}
    product_id = data.get("product_id")
    quantity = data.get("quantity")
    customer_name = data.get("customer_name")
    customer_email = data.get("customer_email")
    promo_code = data.get("promo_code", "")

    if not is_int(product_id) or product_id < 1:
        errors["product_id"] = "Поле product_id обов'язкове й має бути додатним цілим числом."
    if not is_int(quantity) or quantity < 1:
        errors["quantity"] = "Поле quantity обов'язкове й має бути додатним цілим числом."
    cleaned_name, name_err = _validate_nonempty_str(customer_name, 100, "customer_name")
    if name_err:
        errors["customer_name"] = name_err
    if not is_valid_email(customer_email):
        errors["customer_email"] = "Поле customer_email обов'язкове й має містити коректний email."
    if not isinstance(promo_code, str):
        errors["promo_code"] = "Поле promo_code має бути рядком."

    if errors:
        return None, errors
    return {
        "product_id": product_id,
        "quantity": quantity,
        "customer_name": cleaned_name,
        "customer_email": customer_email.strip(),
        "promo_code": promo_code.strip(),
    }, {}


def validate_feedback_payload(data):
    """Валідує вхідні дані для створення відгуку."""
    errors = {}
    cleaned_name, name_err = _validate_nonempty_str(data.get("name"), 100, "name")
    if name_err:
        errors["name"] = name_err
    if not is_valid_email(data.get("email")):
        errors["email"] = "Поле email обов'язкове й має містити коректний email."
    cleaned_msg, msg_err = _validate_nonempty_str(data.get("message"), 2000, "message")
    if msg_err:
        errors["message"] = msg_err

    if errors:
        return None, errors
    return {
        "name": cleaned_name,
        "email": data["email"].strip(),
        "message": cleaned_msg,
    }, {}


def validate_category_payload(data):
    """Валідує вхідні дані категорії."""
    errors = {}
    cleaned_name, name_err = _validate_nonempty_str(data.get("name"), 80, "name")
    if name_err:
        errors["name"] = name_err

    parent_id = data.get("parent_id")
    if parent_id is not None and (not is_int(parent_id) or parent_id < 1):
        errors["parent_id"] = "Поле parent_id має бути додатним цілим числом або null."

    if errors:
        return None, errors
    return {"name": cleaned_name, "parent_id": parent_id}, {}


def validate_promocode_payload(data):
    """Валідує вхідні дані промокоду."""
    errors = {}
    raw_code = data.get("code")
    if not isinstance(raw_code, str) or not _PROMO_RE.fullmatch(raw_code.strip().upper()):
        errors["code"] = "Код має містити 3–32 латинські літери, цифри, дефіс або підкреслення."

    discount_percent = data.get("discount_percent")
    if not is_int(discount_percent) or not 1 <= discount_percent <= 100:
        errors["discount_percent"] = "Поле discount_percent має бути цілим числом від 1 до 100."

    expires_on = data.get("expires_on")
    if expires_on is not None and expires_on != "":
        if not isinstance(expires_on, str):
            errors["expires_on"] = "Поле expires_on має бути рядком у форматі YYYY-MM-DD або null."
        else:
            try:
                date.fromisoformat(expires_on.strip())
                expires_on = expires_on.strip()
            except ValueError:
                errors["expires_on"] = "Поле expires_on має бути коректною датою у форматі YYYY-MM-DD."
    else:
        expires_on = None

    usage_limit = data.get("usage_limit")
    if usage_limit is not None:
        if not is_int(usage_limit) or usage_limit < 1:
            errors["usage_limit"] = "Поле usage_limit має бути додатним цілим числом або null."

    active = data.get("active", True)
    if not isinstance(active, bool):
        errors["active"] = "Поле active має бути булевим значенням (true або false)."

    if errors:
        return None, errors
    return {
        "code": raw_code.strip().upper(),
        "discount_percent": discount_percent,
        "expires_on": expires_on,
        "usage_limit": usage_limit,
        "active": active,
    }, {}


def validate_user_create_payload(data):
    """Валідує дані для створення користувача."""
    errors = {}
    cleaned_name, name_err = _validate_nonempty_str(data.get("name"), 100, "name")
    if name_err:
        errors["name"] = name_err
    if not is_valid_email(data.get("email")):
        errors["email"] = "Поле email обов'язкове й має містити коректний email."
    password = data.get("password")
    if not isinstance(password, str) or len(password) < 8:
        errors["password"] = "Поле password обов'язкове й має містити щонайменше 8 символів."

    if errors:
        return None, errors
    return {
        "name": cleaned_name,
        "email": data["email"].strip().lower(),
        "password": password,
    }, {}


def validate_user_update_payload(data, current_user):
    """Валідує дані для часткового оновлення користувача."""
    errors = {}
    if not data:
        return None, {"_body": "Потрібно передати хоча б одне поле для оновлення."}

    name = current_user["name"]
    email = current_user["email"]
    role = current_user["role"]

    if "name" in data:
        cleaned_name, name_err = _validate_nonempty_str(data.get("name"), 100, "name")
        if name_err:
            errors["name"] = name_err
        else:
            name = cleaned_name

    if "email" in data:
        if not is_valid_email(data.get("email")):
            errors["email"] = "Поле email має містити коректний email."
        else:
            email = data["email"].strip().lower()

    if "role" in data:
        raw_role = data.get("role")
        if raw_role not in ("admin", "customer"):
            errors["role"] = "Поле role має бути 'admin' або 'customer'."
        else:
            role = raw_role

    if errors:
        return None, errors
    return {"name": name, "email": email, "role": role}, {}


def parse_pagination_params():
    """Читає параметри пагінації page і per_page з query string."""
    raw_page = request.args.get("page", "1")
    raw_per_page = request.args.get("per_page", "20")
    errors = {}
    try:
        page = int(raw_page)
        if page < 1:
            raise ValueError
    except ValueError:
        errors["page"] = "Параметр page має бути додатним цілим числом."
        page = 1

    try:
        per_page = int(raw_per_page)
        if not 1 <= per_page <= 100:
            raise ValueError
    except ValueError:
        errors["per_page"] = "Параметр per_page має бути цілим числом від 1 до 100."
        per_page = 20

    if errors:
        return None, None, errors
    return page, per_page, {}


def paginate(items, page, per_page):
    """Повертає зріз елементів для поточної сторінки та метадані пагінації."""
    total = len(items)
    pages = math.ceil(total / per_page) if total else 0
    start = (page - 1) * per_page
    end = start + per_page
    return items[start:end], {
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
    }
