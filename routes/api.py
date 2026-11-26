"""Базовий REST API застосунку LOQ Market у форматі JSON."""
import math
import re
import sqlite3

from flask import Blueprint, current_app, jsonify, request, url_for

import models

api_bp = Blueprint("api", __name__, url_prefix="/api")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SWAGGER_CONFIG = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec_1",
            "route": "/apispec_1.json",
            "rule_filter": lambda rule: rule.rule.startswith("/api/"),
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/apidocs/",
}

SWAGGER_TEMPLATE = {
    "swagger": "2.0",
    "info": {
        "title": "LOQ Market REST API",
        "version": "1.0.0",
        "description": (
            "Документація REST API магазину скінів Counter-Strike 2 (LOQ Market).\n\n"
            "### Загальні правила\n"
            "- Усі запити з тілом мають використовувати `Content-Type: application/json`.\n"
            "- Усі відповіді та помилки повертаються у форматі JSON (`{\"error\": \"...\"}`).\n\n"
            "### Приклади використання (curl)\n"
            "```bash\n"
            "# Отримати всі товари\n"
            "curl http://127.0.0.1:5000/api/products\n\n"
            "# Додати товар\n"
            "curl -X POST http://127.0.0.1:5000/api/products \\\n"
            "  -H 'Content-Type: application/json' \\\n"
            "  -d '{\"weapon\":\"AK-47\",\"skin\":\"Redline\",\"quality\":\"Field-Tested\",\"price\":25.5,\"stock\":4}'\n\n"
            "# Оформити замовлення зі знижкою за промокодом\n"
            "curl -X POST http://127.0.0.1:5000/api/orders \\\n"
            "  -H 'Content-Type: application/json' \\\n"
            "  -d '{\"product_id\":1,\"quantity\":1,\"customer_name\":\"Іван\",\"customer_email\":\"ivan@example.com\",\"promo_code\":\"LOQ10\"}'\n"
            "```"
        ),
    },
    "tags": [
        {"name": "Products", "description": "Керування товарами каталогу (скіни)"},
        {"name": "Categories", "description": "Перегляд категорій товарів"},
        {"name": "Orders", "description": "Створення, перегляд і керування замовленнями"},
        {"name": "Feedback", "description": "Перегляд та надсилання відгуків"},
    ],
    "definitions": {
        "Product": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "example": 1, "description": "Унікальний ідентифікатор товару"},
                "weapon": {"type": "string", "example": "AWP", "description": "Назва зброї"},
                "skin": {"type": "string", "example": "Dragon Lore", "description": "Назва скіну"},
                "quality": {"type": "string", "example": "Factory New", "description": "Стан (якість) скіну"},
                "price": {"type": "number", "format": "float", "example": 1249.0, "description": "Ціна товару"},
                "image_url": {"type": "string", "example": "https://cdn.example.com/awp-dlore.png", "description": "URL зображення"},
                "stock": {"type": "integer", "example": 10, "description": "Залишок на складі"},
                "category_id": {"type": "integer", "x-nullable": True, "example": 5, "description": "ID категорії або null"},
                "category_name": {"type": "string", "x-nullable": True, "example": "Гвинтівки", "description": "Назва категорії"},
            },
        },
        "ProductInput": {
            "type": "object",
            "required": ["weapon", "skin", "quality", "price"],
            "properties": {
                "weapon": {"type": "string", "example": "AK-47", "description": "Назва зброї (непорожній рядок)"},
                "skin": {"type": "string", "example": "Redline", "description": "Назва скіну (непорожній рядок)"},
                "quality": {"type": "string", "example": "Field-Tested", "description": "Стан скіну (непорожній рядок)"},
                "price": {"type": "number", "minimum": 0, "example": 25.5, "description": "Ціна (>= 0)"},
                "image_url": {"type": "string", "example": "https://cdn.example.com/ak47-redline.png", "description": "URL зображення (необов'язково)"},
                "stock": {"type": "integer", "minimum": 0, "default": 10, "example": 5, "description": "Кількість на складі (>= 0, за замовчуванням 10)"},
                "category_id": {"type": "integer", "x-nullable": True, "example": 5, "description": "ID існуючої категорії або null"},
            },
            "example": {
                "weapon": "AK-47",
                "skin": "Redline",
                "quality": "Field-Tested",
                "price": 25.5,
                "image_url": "https://cdn.example.com/ak47-redline.png",
                "stock": 5,
                "category_id": 5,
            },
        },
        "Category": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "example": 5},
                "name": {"type": "string", "example": "Гвинтівки"},
                "parent_id": {"type": "integer", "x-nullable": True, "example": 2},
                "depth": {"type": "integer", "example": 2},
                "path": {"type": "string", "example": "Скіни CS2 / Зброя / Гвинтівки"},
            },
        },
        "OrderItem": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "example": 1},
                "product_id": {"type": "integer", "example": 1},
                "product_name": {"type": "string", "example": "AWP | Dragon Lore"},
                "unit_price": {"type": "number", "format": "float", "example": 1249.0},
                "quantity": {"type": "integer", "example": 1},
                "weapon": {"type": "string", "example": "AWP"},
                "skin": {"type": "string", "example": "Dragon Lore"},
            },
        },
        "OrderSummary": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "example": 1},
                "user_id": {"type": "integer", "x-nullable": True, "example": 2},
                "customer_name": {"type": "string", "example": "Іван Петренко"},
                "customer_email": {"type": "string", "example": "ivan@example.com"},
                "total_price": {"type": "number", "format": "float", "example": 1124.1},
                "promo_code": {"type": "string", "x-nullable": True, "example": "LOQ10"},
                "discount_amount": {"type": "number", "format": "float", "example": 124.9},
                "status": {
                    "type": "string",
                    "enum": ["pending", "processing", "shipped", "completed", "cancelled"],
                    "example": "pending",
                },
                "created_at": {"type": "string", "example": "2026-11-26 20:00:00"},
                "items": {"type": "string", "example": "AWP | Dragon Lore × 1"},
            },
        },
        "OrderDetail": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "example": 1},
                "user_id": {"type": "integer", "x-nullable": True, "example": 2},
                "customer_name": {"type": "string", "example": "Іван Петренко"},
                "customer_email": {"type": "string", "example": "ivan@example.com"},
                "total_price": {"type": "number", "format": "float", "example": 1124.1},
                "promo_code": {"type": "string", "x-nullable": True, "example": "LOQ10"},
                "discount_amount": {"type": "number", "format": "float", "example": 124.9},
                "status": {
                    "type": "string",
                    "enum": ["pending", "processing", "shipped", "completed", "cancelled"],
                    "example": "pending",
                },
                "created_at": {"type": "string", "example": "2026-11-26 20:00:00"},
                "items": {"type": "array", "items": {"$ref": "#/definitions/OrderItem"}},
            },
        },
        "OrderCreateInput": {
            "type": "object",
            "required": ["product_id", "quantity", "customer_name", "customer_email"],
            "properties": {
                "product_id": {"type": "integer", "minimum": 1, "example": 1, "description": "ID товару"},
                "quantity": {"type": "integer", "minimum": 1, "example": 1, "description": "Кількість одиниць (>= 1)"},
                "customer_name": {"type": "string", "example": "Іван Петренко", "description": "Ім'я покупця"},
                "customer_email": {"type": "string", "format": "email", "example": "ivan@example.com", "description": "Email покупця"},
                "promo_code": {"type": "string", "example": "LOQ10", "description": "Промокод для знижки (необов'язково)"},
            },
            "example": {
                "product_id": 1,
                "quantity": 1,
                "customer_name": "Іван Петренко",
                "customer_email": "ivan@example.com",
                "promo_code": "LOQ10",
            },
        },
        "OrderStatusInput": {
            "type": "object",
            "required": ["status"],
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "processing", "shipped", "completed", "cancelled"],
                    "example": "processing",
                    "description": "Новий статус замовлення",
                },
            },
            "example": {"status": "processing"},
        },
        "Feedback": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "example": 1},
                "name": {"type": "string", "example": "Олена Коваль"},
                "email": {"type": "string", "example": "olena@example.com"},
                "message": {"type": "string", "example": "Швидке оформлення та зручний каталог!"},
                "created_at": {"type": "string", "example": "2026-11-26 20:15:00"},
            },
        },
        "FeedbackCreateResponse": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "example": 1},
                "name": {"type": "string", "example": "Олена Коваль"},
                "email": {"type": "string", "example": "olena@example.com"},
                "message": {"type": "string", "example": "Швидке оформлення та зручний каталог!"},
            },
        },
        "FeedbackInput": {
            "type": "object",
            "required": ["name", "email", "message"],
            "properties": {
                "name": {"type": "string", "example": "Олена Коваль", "description": "Ім'я автора відгуку"},
                "email": {"type": "string", "format": "email", "example": "olena@example.com", "description": "Email автора"},
                "message": {"type": "string", "example": "Швидке оформлення та зручний каталог!", "description": "Текст відгуку"},
            },
            "example": {
                "name": "Олена Коваль",
                "email": "olena@example.com",
                "message": "Швидке оформлення та зручний каталог!",
            },
        },
        "ErrorResponse": {
            "type": "object",
            "properties": {
                "error": {"type": "string", "example": "Ресурс не знайдено."},
            },
        },
    },
}


def error_response(message, status):
    """Повертає JSON-повідомлення про помилку разом із HTTP-кодом статусу."""
    return jsonify({"error": message}), status


@api_bp.errorhandler(sqlite3.Error)
def handle_database_error(error):
    """Обробляє помилки SQLite у межах API та повертає JSON-відповідь."""
    current_app.logger.exception("Помилка бази даних в API", exc_info=error)
    return error_response("Помилка роботи з базою даних.", 500)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_valid_email(value):
    return isinstance(value, str) and bool(_EMAIL_RE.fullmatch(value.strip()))


def _get_json_object():
    if not request.is_json:
        return None, error_response("Запит повинен мати заголовок Content-Type: application/json.", 400)
    data = request.get_json(silent=True)
    if data is None:
        return None, error_response("Некоректний JSON у тілі запиту.", 400)
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
    """Отримати список усіх товарів каталогу
    ---
    tags:
      - Products
    produces:
      - application/json
    responses:
      200:
        description: Список товарів каталогу у форматі JSON
        schema:
          type: array
          items:
            $ref: '#/definitions/Product'
        examples:
          application/json:
            - id: 1
              weapon: AWP
              skin: Dragon Lore
              quality: Factory New
              price: 1249.0
              image_url: https://cdn.example.com/awp-dlore.png
              stock: 10
              category_id: 5
              category_name: Гвинтівки
      500:
        description: Помилка сервера або бази даних
        schema:
          $ref: '#/definitions/ErrorResponse'
    """
    products = [dict(row) for row in models.get_products()]
    return jsonify(products), 200


@api_bp.route("/products/<int:product_id>", methods=["GET"])
def get_product(product_id):
    """Отримати один товар за ідентифікатором
    ---
    tags:
      - Products
    produces:
      - application/json
    parameters:
      - name: product_id
        in: path
        type: integer
        required: true
        description: Ідентифікатор товару
        example: 1
    responses:
      200:
        description: Дані знайденого товару
        schema:
          $ref: '#/definitions/Product'
        examples:
          application/json:
            id: 1
            weapon: AWP
            skin: Dragon Lore
            quality: Factory New
            price: 1249.0
            image_url: https://cdn.example.com/awp-dlore.png
            stock: 10
            category_id: 5
            category_name: Гвинтівки
      404:
        description: Товар не знайдено
        schema:
          $ref: '#/definitions/ErrorResponse'
        examples:
          application/json:
            error: "Товар не знайдено."
    """
    product = models.get_product(product_id)
    if product is None:
        return error_response("Товар не знайдено.", 404)
    return jsonify(dict(product)), 200


@api_bp.route("/products", methods=["POST"])
def create_product():
    """Створити новий товар у каталозі
    ---
    tags:
      - Products
    consumes:
      - application/json
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        description: Дані нового товару
        schema:
          $ref: '#/definitions/ProductInput'
    responses:
      201:
        description: Товар успішно створено (у заголовку Location повертається URL ресурсу)
        headers:
          Location:
            type: string
            description: Адреса створеного товару (/api/products/{id})
        schema:
          $ref: '#/definitions/Product'
        examples:
          application/json:
            id: 10
            weapon: AK-47
            skin: Redline
            quality: Field-Tested
            price: 25.5
            image_url: https://cdn.example.com/ak47-redline.png
            stock: 5
            category_id: 5
            category_name: Гвинтівки
      400:
        description: Некоректний JSON або помилка валідації полів
        schema:
          $ref: '#/definitions/ErrorResponse'
        examples:
          application/json:
            error: "Поле price обов'язкове й має бути числом не менше 0."
    """
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
    """Повністю оновити існуючий товар
    ---
    tags:
      - Products
    consumes:
      - application/json
    produces:
      - application/json
    parameters:
      - name: product_id
        in: path
        type: integer
        required: true
        description: Ідентифікатор товару для оновлення
        example: 1
      - name: body
        in: body
        required: true
        description: Повний набір полів товару
        schema:
          $ref: '#/definitions/ProductInput'
    responses:
      200:
        description: Товар успішно оновлено
        schema:
          $ref: '#/definitions/Product'
      400:
        description: Некоректний JSON або помилка валідації полів
        schema:
          $ref: '#/definitions/ErrorResponse'
      404:
        description: Товар не знайдено
        schema:
          $ref: '#/definitions/ErrorResponse'
        examples:
          application/json:
            error: "Товар не знайдено."
    """
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
    """Видалити товар за ідентифікатором
    ---
    tags:
      - Products
    produces:
      - application/json
    parameters:
      - name: product_id
        in: path
        type: integer
        required: true
        description: Ідентифікатор товару для видалення
        example: 10
    responses:
      204:
        description: Товар успішно видалено (порожнє тіло відповіді)
      404:
        description: Товар не знайдено
        schema:
          $ref: '#/definitions/ErrorResponse'
        examples:
          application/json:
            error: "Товар не знайдено."
      409:
        description: Конфлікт — товар входить до існуючих замовлень
        schema:
          $ref: '#/definitions/ErrorResponse'
        examples:
          application/json:
            error: "Не можна видалити товар, який входить до замовлень."
    """
    if models.get_product(product_id) is None:
        return error_response("Товар не знайдено.", 404)

    if not models.delete_product(product_id):
        return error_response("Не можна видалити товар, який входить до замовлень.", 409)
    return "", 204


@api_bp.route("/categories", methods=["GET"])
def get_categories():
    """Отримати список категорій товарів
    ---
    tags:
      - Categories
    produces:
      - application/json
    responses:
      200:
        description: Ієрархічний список категорій каталогу
        schema:
          type: array
          items:
            $ref: '#/definitions/Category'
        examples:
          application/json:
            - id: 1
              name: Скіни CS2
              parent_id: null
              depth: 0
              path: Скіни CS2
            - id: 5
              name: Гвинтівки
              parent_id: 2
              depth: 2
              path: Скіни CS2 / Зброя / Гвинтівки
    """
    return jsonify(models.get_categories()), 200


@api_bp.route("/orders", methods=["GET"])
def get_orders():
    """Отримати список усіх замовлень
    ---
    tags:
      - Orders
    produces:
      - application/json
    responses:
      200:
        description: Перелік замовлень у системі
        schema:
          type: array
          items:
            $ref: '#/definitions/OrderSummary'
        examples:
          application/json:
            - id: 1
              user_id: 2
              customer_name: Іван Петренко
              customer_email: ivan@example.com
              total_price: 1124.1
              promo_code: LOQ10
              discount_amount: 124.9
              status: pending
              created_at: "2026-11-26 20:00:00"
              items: "AWP | Dragon Lore × 1"
    """
    orders = [dict(row) for row in models.get_orders()]
    return jsonify(orders), 200


@api_bp.route("/orders/<int:order_id>", methods=["GET"])
def get_order(order_id):
    """Отримати замовлення за ідентифікатором
    ---
    tags:
      - Orders
    produces:
      - application/json
    parameters:
      - name: order_id
        in: path
        type: integer
        required: true
        description: Ідентифікатор замовлення
        example: 1
    responses:
      200:
        description: Детальна інформація про замовлення та його позиції
        schema:
          $ref: '#/definitions/OrderDetail'
      404:
        description: Замовлення не знайдено
        schema:
          $ref: '#/definitions/ErrorResponse'
        examples:
          application/json:
            error: "Замовлення не знайдено."
    """
    order = models.get_order(order_id)
    if order is None:
        return error_response("Замовлення не знайдено.", 404)
    return jsonify(order), 200


@api_bp.route("/orders", methods=["POST"])
def create_order():
    """Створити нове замовлення
    ---
    tags:
      - Orders
    consumes:
      - application/json
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        description: Параметри замовлення та контактні дані покупця
        schema:
          $ref: '#/definitions/OrderCreateInput'
    responses:
      201:
        description: Замовлення успішно оформлено
        headers:
          Location:
            type: string
            description: Адреса створеного замовлення (/api/orders/{id})
        schema:
          $ref: '#/definitions/OrderDetail'
      400:
        description: Некоректні дані, недостатньо товару на складі або недійсний промокод
        schema:
          $ref: '#/definitions/ErrorResponse'
        examples:
          application/json:
            error: "Недостатньо товару на складі."
      404:
        description: Товар із вказаним product_id не знайдено
        schema:
          $ref: '#/definitions/ErrorResponse'
        examples:
          application/json:
            error: "Товар не знайдено."
    """
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
    if not _is_valid_email(customer_email):
        return error_response("Поле customer_email обов'язкове й має містити коректний email.", 400)
    if not isinstance(promo_code, str):
        return error_response("Поле promo_code має бути рядком.", 400)

    if models.get_product(product_id) is None:
        return error_response("Товар не знайдено.", 404)

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
    """Оновити статус замовлення
    ---
    tags:
      - Orders
    consumes:
      - application/json
    produces:
      - application/json
    parameters:
      - name: order_id
        in: path
        type: integer
        required: true
        description: Ідентифікатор замовлення
        example: 1
      - name: body
        in: body
        required: true
        description: Новий статус замовлення
        schema:
          $ref: '#/definitions/OrderStatusInput'
    responses:
      200:
        description: Статус замовлення оновлено
        schema:
          $ref: '#/definitions/OrderDetail'
      400:
        description: Недопустимий статус або нестача товару при відновленні скасованого замовлення
        schema:
          $ref: '#/definitions/ErrorResponse'
        examples:
          application/json:
            error: "Поле status має бути одним із: pending, processing, shipped, completed, cancelled."
      404:
        description: Замовлення не знайдено
        schema:
          $ref: '#/definitions/ErrorResponse'
    """
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
    """Видалити замовлення за ідентифікатором
    ---
    tags:
      - Orders
    produces:
      - application/json
    parameters:
      - name: order_id
        in: path
        type: integer
        required: true
        description: Ідентифікатор замовлення для видалення
        example: 1
    responses:
      204:
        description: Замовлення видалено (залишок повернено на склад, якщо воно не було скасоване)
      404:
        description: Замовлення не знайдено
        schema:
          $ref: '#/definitions/ErrorResponse'
        examples:
          application/json:
            error: "Замовлення не знайдено."
    """
    if not models.delete_order(order_id):
        return error_response("Замовлення не знайдено.", 404)
    return "", 204


@api_bp.route("/feedback", methods=["GET"])
def get_feedback():
    """Отримати список усіх відгуків
    ---
    tags:
      - Feedback
    produces:
      - application/json
    responses:
      200:
        description: Перелік збережених відгуків користувачів
        schema:
          type: array
          items:
            $ref: '#/definitions/Feedback'
        examples:
          application/json:
            - id: 1
              name: Олена Коваль
              email: olena@example.com
              message: Швидке оформлення та зручний каталог!
              created_at: "2026-11-26 20:15:00"
    """
    entries = [dict(row) for row in models.get_all_feedback()]
    return jsonify(entries), 200


@api_bp.route("/feedback", methods=["POST"])
def create_feedback():
    """Зберегти новий відгук користувача
    ---
    tags:
      - Feedback
    consumes:
      - application/json
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        description: Дані відгуку користувача
        schema:
          $ref: '#/definitions/FeedbackInput'
    responses:
      201:
        description: Відгук успішно збережено
        schema:
          $ref: '#/definitions/FeedbackCreateResponse'
        examples:
          application/json:
            id: 1
            name: Олена Коваль
            email: olena@example.com
            message: Швидке оформлення та зручний каталог!
      400:
        description: Некоректний JSON або помилка валідації полів
        schema:
          $ref: '#/definitions/ErrorResponse'
        examples:
          application/json:
            error: "Поле email обов'язкове й має містити коректний email."
    """
    data, err = _get_json_object()
    if err is not None:
        return err

    name = data.get("name")
    email = data.get("email")
    message = data.get("message")

    if not isinstance(name, str) or not name.strip():
        return error_response("Поле name обов'язкове й має бути непорожнім рядком.", 400)
    if not _is_valid_email(email):
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
