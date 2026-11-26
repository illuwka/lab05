"""Базовий REST API застосунку LOQ Market у форматі JSON."""
import math

from flask import Blueprint, jsonify, request, url_for

import models

api_bp = Blueprint("api", __name__, url_prefix="/api")


def error_response(message, status):
    """Повертає JSON-повідомлення про помилку разом із HTTP-кодом статусу."""
    return jsonify({"error": message}), status


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _get_json_object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, error_response("Тіло запиту має бути JSON-об'єктом.", 400)
    return data, None


def _parse_product_payload(data):
    """Валідує та нормалізує JSON-поля товару для створення й оновлення."""
    for field in ("weapon", "skin", "quality"):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            return None, f"Поле {field} обов'язкове й має бути непорожнім рядком."

    price = data.get("price")
    if not _is_number(price) or price < 0:
        return None, "Поле price обов'язкове й має бути числом не менше 0."

    stock = data.get("stock", 10)
    if not _is_int(stock) or stock < 0:
        return None, "Поле stock має бути цілим невід'ємним числом."

    image_url = data.get("image_url", "")
    if not isinstance(image_url, str):
        return None, "Поле image_url має бути рядком."

    category_id = data.get("category_id")
    if category_id is not None:
        if not _is_int(category_id):
            return None, "Поле category_id має бути цілим числом або null."
        category_ids = {category["id"] for category in models.get_categories()}
        if category_id not in category_ids:
            return None, "Вказану категорію не знайдено."

    return {
        "weapon": data["weapon"].strip(),
        "skin": data["skin"].strip(),
        "quality": data["quality"].strip(),
        "price": round(float(price), 2),
        "image_url": image_url.strip(),
        "stock": stock,
        "category_id": category_id,
    }, None


@api_bp.route("/products", methods=["GET"])
def get_products():
    """Повертає список усіх товарів каталогу."""
    products = [dict(row) for row in models.get_products()]
    return jsonify(products), 200


@api_bp.route("/products/<int:product_id>", methods=["GET"])
def get_product(product_id):
    """Повертає один товар за ідентифікатором."""
    product = models.get_product(product_id)
    if product is None:
        return error_response("Товар не знайдено.", 404)
    return jsonify(dict(product)), 200


@api_bp.route("/products", methods=["POST"])
def create_product():
    """Створює новий товар у каталозі."""
    data, err = _get_json_object()
    if err is not None:
        return err

    parsed, message = _parse_product_payload(data)
    if message:
        return error_response(message, 400)

    product_id = models.save_product(
        None,
        parsed["weapon"],
        parsed["skin"],
        parsed["quality"],
        parsed["price"],
        parsed["image_url"],
        parsed["stock"],
        parsed["category_id"],
    )
    created = dict(models.get_product(product_id))
    return jsonify(created), 201, {"Location": url_for("api.get_product", product_id=product_id)}


@api_bp.route("/products/<int:product_id>", methods=["PUT"])
def update_product(product_id):
    """Повністю оновлює існуючий товар."""
    if models.get_product(product_id) is None:
        return error_response("Товар не знайдено.", 404)

    data, err = _get_json_object()
    if err is not None:
        return err

    parsed, message = _parse_product_payload(data)
    if message:
        return error_response(message, 400)

    models.save_product(
        product_id,
        parsed["weapon"],
        parsed["skin"],
        parsed["quality"],
        parsed["price"],
        parsed["image_url"],
        parsed["stock"],
        parsed["category_id"],
    )
    updated = dict(models.get_product(product_id))
    return jsonify(updated), 200


@api_bp.route("/products/<int:product_id>", methods=["DELETE"])
def delete_product(product_id):
    """Видаляє товар, якщо він не входить до жодного замовлення."""
    if models.get_product(product_id) is None:
        return error_response("Товар не знайдено.", 404)

    if not models.delete_product(product_id):
        return error_response("Не можна видалити товар, який входить до замовлень.", 409)
    return "", 204


@api_bp.route("/categories", methods=["GET"])
def get_categories():
    """Повертає список категорій товарів."""
    return jsonify(models.get_categories()), 200


@api_bp.route("/orders", methods=["GET"])
def get_orders():
    """Повертає список усіх замовлень."""
    orders = [dict(row) for row in models.get_orders()]
    return jsonify(orders), 200


@api_bp.route("/orders/<int:order_id>", methods=["GET"])
def get_order(order_id):
    """Повертає замовлення за ідентифікатором разом із переліком позицій."""
    order = models.get_order(order_id)
    if order is None:
        return error_response("Замовлення не знайдено.", 404)
    return jsonify(order), 200


@api_bp.route("/orders", methods=["POST"])
def create_order():
    """Створює нове замовлення для вказаного товару та покупця."""
    data, err = _get_json_object()
    if err is not None:
        return err

    product_id = data.get("product_id")
    quantity = data.get("quantity")
    customer_name = data.get("customer_name")
    customer_email = data.get("customer_email")
    promo_code = data.get("promo_code", "")

    if not _is_int(product_id) or product_id < 1:
        return error_response("Поле product_id обов'язкове й має бути додатним цілим числом.", 400)
    if not _is_int(quantity) or quantity < 1:
        return error_response("Поле quantity обов'язкове й має бути додатним цілим числом.", 400)
    if not isinstance(customer_name, str) or not customer_name.strip():
        return error_response("Поле customer_name обов'язкове й має бути непорожнім рядком.", 400)
    if not isinstance(customer_email, str) or "@" not in customer_email or not customer_email.strip():
        return error_response("Поле customer_email обов'язкове й має містити коректний email.", 400)
    if not isinstance(promo_code, str):
        return error_response("Поле promo_code має бути рядком.", 400)

    try:
        order_id = models.create_order(
            product_id=product_id,
            customer_name=customer_name,
            customer_email=customer_email,
            quantity=quantity,
            promo_code=promo_code,
        )
    except ValueError as error:
        return error_response(str(error), 400)

    created = models.get_order(order_id)
    return jsonify(created), 201, {"Location": url_for("api.get_order", order_id=order_id)}


@api_bp.route("/orders/<int:order_id>", methods=["PATCH"])
def update_order_status(order_id):
    """Оновлює статус існуючого замовлення."""
    if models.get_order(order_id) is None:
        return error_response("Замовлення не знайдено.", 404)

    data, err = _get_json_object()
    if err is not None:
        return err

    status = data.get("status")
    if not isinstance(status, str) or status not in models.ORDER_STATUSES:
        allowed = ", ".join(models.ORDER_STATUSES)
        return error_response(f"Поле status має бути одним із: {allowed}.", 400)

    try:
        models.update_order_status(order_id, status)
    except ValueError as error:
        return error_response(str(error), 400)

    return jsonify(models.get_order(order_id)), 200


@api_bp.route("/orders/<int:order_id>", methods=["DELETE"])
def delete_order(order_id):
    """Видаляє замовлення (і повертає залишок на склад, якщо воно не було скасоване)."""
    if not models.delete_order(order_id):
        return error_response("Замовлення не знайдено.", 404)
    return "", 204


@api_bp.route("/feedback", methods=["GET"])
def get_feedback():
    """Повертає список усіх відгуків."""
    entries = [dict(row) for row in models.get_all_feedback()]
    return jsonify(entries), 200


@api_bp.route("/feedback", methods=["POST"])
def create_feedback():
    """Зберігає новий відгук користувача."""
    data, err = _get_json_object()
    if err is not None:
        return err

    name = data.get("name")
    email = data.get("email")
    message = data.get("message")

    if not isinstance(name, str) or not name.strip():
        return error_response("Поле name обов'язкове й має бути непорожнім рядком.", 400)
    if not isinstance(email, str) or "@" not in email or not email.strip():
        return error_response("Поле email обов'язкове й має містити коректний email.", 400)
    if not isinstance(message, str) or not message.strip():
        return error_response("Поле message обов'язкове й має бути непорожнім рядком.", 400)

    feedback_id = models.create_feedback(name, email, message)
    return (
        jsonify(
            {
                "id": feedback_id,
                "name": name.strip(),
                "email": email.strip(),
                "message": message.strip(),
            }
        ),
        201,
    )
