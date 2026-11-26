"""REST API v1 застосунку LOQ Market (та сумісний неверсіонований префікс /api)."""
from flask import Blueprint, request, url_for, jsonify

import models
from .api_common import (
    error_response,
    parse_json_object,
    register_db_error_handler,
    validate_feedback_payload,
    validate_order_payload,
    validate_product_payload,
)

api_bp = Blueprint("api", __name__, url_prefix="/api")
api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")

register_db_error_handler(api_bp, v2=False)
register_db_error_handler(api_v1_bp, v2=False)


@api_bp.after_request
@api_v1_bp.after_request
def add_v1_version_header(response):
    """Додає заголовок версії API для клієнтів."""
    response.headers.setdefault("X-API-Version", "1.0")
    return response


def _v1_route(rule, **options):
    """Реєструє маршрут одночасно на /api/... та /api/v1/... без дублювання коду."""

    def decorator(func):
        api_bp.add_url_rule(rule, view_func=func, **options)
        api_v1_bp.add_url_rule(rule, view_func=func, **options)
        return func

    return decorator


def _first_error(errors):
    return next(iter(errors.values()))


SWAGGER_CONFIG = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec_v2",
            "name": "LOQ Market API v2 (Повне API)",
            "version": "2.0.0",
            "route": "/apispec_v2.json",
            "rule_filter": lambda rule: rule.rule.startswith("/api/v2/"),
            "model_filter": lambda tag: True,
        },
        {
            "endpoint": "apispec_v1",
            "name": "LOQ Market API v1 (Базове API)",
            "version": "1.0.0",
            "route": "/apispec_v1.json",
            "rule_filter": lambda rule: rule.rule.startswith("/api/v1/"),
            "model_filter": lambda tag: True,
        },
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/apidocs/",
}

SWAGGER_TEMPLATE = {
    "swagger": "2.0",
    "info": {
        "title": "LOQ Market REST API",
        "version": "2.0.0",
        "description": (
            "Документація REST API магазину скінів Counter-Strike 2 (LOQ Market).\n\n"
            "### Версії API\n"
            "- **v1 (`/api/v1/...`, а також `/api/...`)** — базовий REST API (товари, категорії, замовлення, відгуки).\n"
            "- **v2 (`/api/v2/...`)** — повне API для всіх сутностей (товари, категорії, замовлення, промокоди, "
            "користувачі, відгуки) із фільтрацією, сортуванням, пагінацією, `PATCH` для товарів і користувачів та "
            "деталізованими помилками валідації (`422`, `409`, `415`).\n\n"
            "Перемикайте версію специфікації у випадаючому списку **Select a definition** у верхній панелі.\n\n"
            "### Приклади використання (curl)\n"
            "```bash\n"
            "# API v1: отримати всі товари\n"
            "curl http://127.0.0.1:5000/api/v1/products\n\n"
            "# API v2: пошук і пагінація товарів\n"
            "curl 'http://127.0.0.1:5000/api/v2/products?q=AWP&sort=price_desc&page=1&per_page=5'\n\n"
            "# API v2: часткове оновлення ціни товару\n"
            "curl -X PATCH http://127.0.0.1:5000/api/v2/products/1 \\\n"
            "  -H 'Content-Type: application/json' \\\n"
            "  -d '{\"price\": 1199.0}'\n"
            "```"
        ),
    },
    "tags": [
        {"name": "Products", "description": "Керування товарами каталогу (скіни)"},
        {"name": "Categories", "description": "Керування ієрархічними категоріями товарів"},
        {"name": "Orders", "description": "Створення, перегляд і керування замовленнями"},
        {"name": "Promocodes", "description": "Керування промокодами знижок (v2)"},
        {"name": "Users", "description": "Керування користувачами (v2)"},
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
        "ProductPatchInput": {
            "type": "object",
            "properties": {
                "weapon": {"type": "string", "example": "AK-47"},
                "skin": {"type": "string", "example": "Redline"},
                "quality": {"type": "string", "example": "Minimal Wear"},
                "price": {"type": "number", "minimum": 0, "example": 29.99},
                "image_url": {"type": "string", "example": "https://cdn.example.com/ak47-redline.png"},
                "stock": {"type": "integer", "minimum": 0, "example": 8},
                "category_id": {"type": "integer", "x-nullable": True, "example": 5},
            },
            "example": {"price": 29.99, "stock": 8},
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
        "CategoryInput": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string", "example": "Снайперські гвинтівки"},
                "parent_id": {"type": "integer", "x-nullable": True, "example": 2},
            },
            "example": {"name": "Снайперські гвинтівки", "parent_id": 2},
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
        "Promocode": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "example": 1},
                "code": {"type": "string", "example": "LOQ10"},
                "discount_percent": {"type": "integer", "example": 10},
                "active": {"type": "integer", "example": 1},
                "expires_on": {"type": "string", "x-nullable": True, "example": "2027-12-31"},
                "usage_limit": {"type": "integer", "x-nullable": True, "example": 100},
                "used_count": {"type": "integer", "example": 2},
                "created_at": {"type": "string", "example": "2026-11-26 20:00:00"},
            },
        },
        "PromocodeInput": {
            "type": "object",
            "required": ["code", "discount_percent"],
            "properties": {
                "code": {"type": "string", "example": "WINTER15"},
                "discount_percent": {"type": "integer", "minimum": 1, "maximum": 100, "example": 15},
                "expires_on": {"type": "string", "x-nullable": True, "example": "2027-12-31"},
                "usage_limit": {"type": "integer", "x-nullable": True, "minimum": 1, "example": 50},
                "active": {"type": "boolean", "default": True, "example": True},
            },
            "example": {
                "code": "WINTER15",
                "discount_percent": 15,
                "expires_on": "2027-12-31",
                "usage_limit": 50,
                "active": True,
            },
        },
        "User": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "example": 1},
                "name": {"type": "string", "example": "Іван Петренко"},
                "email": {"type": "string", "example": "ivan@example.com"},
                "role": {"type": "string", "enum": ["customer", "admin"], "example": "customer"},
                "created_at": {"type": "string", "example": "2026-11-26 20:00:00"},
                "orders_count": {"type": "integer", "example": 1},
                "total_spent": {"type": "number", "format": "float", "example": 1124.1},
                "orders": {"type": "array", "items": {"$ref": "#/definitions/OrderSummary"}},
            },
        },
        "UserCreateInput": {
            "type": "object",
            "required": ["name", "email", "password"],
            "properties": {
                "name": {"type": "string", "example": "Марія Коваленко"},
                "email": {"type": "string", "format": "email", "example": "maria@example.com"},
                "password": {"type": "string", "minLength": 8, "example": "StrongPass123"},
            },
            "example": {
                "name": "Марія Коваленко",
                "email": "maria@example.com",
                "password": "StrongPass123",
            },
        },
        "UserUpdateInput": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "example": "Марія Оновлена"},
                "email": {"type": "string", "format": "email", "example": "maria.new@example.com"},
                "role": {"type": "string", "enum": ["customer", "admin"], "example": "customer"},
            },
            "example": {"name": "Марія Оновлена", "role": "customer"},
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
        "PaginationMeta": {
            "type": "object",
            "properties": {
                "page": {"type": "integer", "example": 1},
                "per_page": {"type": "integer", "example": 20},
                "total": {"type": "integer", "example": 9},
                "pages": {"type": "integer", "example": 1},
            },
        },
        "ErrorResponse": {
            "type": "object",
            "properties": {
                "error": {"type": "string", "example": "Ресурс не знайдено."},
            },
        },
        "V2ErrorResponse": {
            "type": "object",
            "properties": {
                "error": {"type": "string", "example": "Помилка валідації вхідних даних."},
                "code": {"type": "string", "example": "VALIDATION_ERROR"},
                "status": {"type": "integer", "example": 422},
                "details": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "example": {"price": "Поле price обов'язкове й має бути числом не менше 0."},
                },
            },
        },
    },
}


@_v1_route("/products", methods=["GET"])
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


@_v1_route("/products/<int:product_id>", methods=["GET"])
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


@_v1_route("/products", methods=["POST"])
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
            description: Адреса створеного товару (/api/v1/products/{id})
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
    data, err = parse_json_object(v2=False)
    if err is not None:
        return err

    parsed, errors = validate_product_payload(data)
    if errors:
        return error_response(_first_error(errors), 400)

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
    return jsonify(created), 201, {"Location": url_for(f"{request.blueprint}.get_product", product_id=product_id)}


@_v1_route("/products/<int:product_id>", methods=["PUT"])
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

    data, err = parse_json_object(v2=False)
    if err is not None:
        return err

    parsed, errors = validate_product_payload(data)
    if errors:
        return error_response(_first_error(errors), 400)

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


@_v1_route("/products/<int:product_id>", methods=["DELETE"])
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


@_v1_route("/categories", methods=["GET"])
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


@_v1_route("/orders", methods=["GET"])
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


@_v1_route("/orders/<int:order_id>", methods=["GET"])
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


@_v1_route("/orders", methods=["POST"])
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
            description: Адреса створеного замовлення (/api/v1/orders/{id})
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
    data, err = parse_json_object(v2=False)
    if err is not None:
        return err

    parsed, errors = validate_order_payload(data)
    if errors:
        return error_response(_first_error(errors), 400)

    if models.get_product(parsed["product_id"]) is None:
        return error_response("Товар не знайдено.", 404)

    try:
        order_id = models.create_order(**parsed)
    except ValueError as error:
        return error_response(str(error), 400)

    created = models.get_order(order_id)
    return jsonify(created), 201, {"Location": url_for(f"{request.blueprint}.get_order", order_id=order_id)}


@_v1_route("/orders/<int:order_id>", methods=["PATCH"])
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

    data, err = parse_json_object(v2=False)
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


@_v1_route("/orders/<int:order_id>", methods=["DELETE"])
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


@_v1_route("/feedback", methods=["GET"])
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


@_v1_route("/feedback", methods=["POST"])
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
    data, err = parse_json_object(v2=False)
    if err is not None:
        return err

    parsed, errors = validate_feedback_payload(data)
    if errors:
        return error_response(_first_error(errors), 400)

    feedback_id = models.create_feedback(parsed["name"], parsed["email"], parsed["message"])
    return jsonify({"id": feedback_id, **parsed}), 201
