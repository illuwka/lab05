"""Повний REST API v2 застосунку LOQ Market з валідацією, фільтрацією, пагінацією та деталізованими помилками."""
from flask import Blueprint, jsonify, request, url_for

import models
from .api_common import (
    paginate,
    parse_json_object,
    parse_pagination_params,
    register_db_error_handler,
    v2_error_response,
    validate_category_payload,
    validate_feedback_payload,
    validate_order_payload,
    validate_product_payload,
    validate_promocode_payload,
    validate_user_create_payload,
    validate_user_update_payload,
)

api_v2_bp = Blueprint("api_v2", __name__, url_prefix="/api/v2")
register_db_error_handler(api_v2_bp, v2=True)


@api_v2_bp.after_request
def add_v2_version_header(response):
    """Додає заголовок версії API v2 до кожної відповіді."""
    response.headers.setdefault("X-API-Version", "2.0")
    return response


def _validation_error(details):
    return v2_error_response("Помилка валідації вхідних даних.", 422, "VALIDATION_ERROR", details)


def _save_product_fields(product_id, fields):
    return models.save_product(
        product_id,
        fields["weapon"],
        fields["skin"],
        fields["quality"],
        fields["price"],
        fields["image_url"],
        fields["stock"],
        fields["category_id"],
    )


def _parse_optional_float(name, details):
    raw = request.args.get(name)
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
        if value < 0:
            raise ValueError
        return value
    except ValueError:
        details[name] = f"Параметр {name} має бути невід'ємним числом."
        return None


def _parse_optional_int(name, details):
    raw = request.args.get(name)
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
        if value < 1:
            raise ValueError
        return value
    except ValueError:
        details[name] = f"Параметр {name} має бути додатним цілим числом."
        return None


def _collect_category_subtree(root_id):
    categories = models.get_categories()
    selected = {root_id}
    while True:
        children = {c["id"] for c in categories if c["parent_id"] in selected}
        updated = selected | children
        if updated == selected:
            return updated
        selected = updated


# --------------------------------------------------------------------- Products


@api_v2_bp.route("/products", methods=["GET"])
def get_products():
    """Отримати список товарів із фільтрацією, сортуванням і пагінацією
    ---
    tags:
      - Products
    produces:
      - application/json
    parameters:
      - name: q
        in: query
        type: string
        description: Пошук за зброєю, скіном або якістю
      - name: weapon
        in: query
        type: string
        description: Фільтр за точною назвою зброї
      - name: quality
        in: query
        type: string
        description: Фільтр за станом скіну
      - name: category_id
        in: query
        type: integer
        description: Фільтр за категорією (включно з підкатегоріями)
      - name: in_stock
        in: query
        type: string
        enum: ["true", "false"]
        description: Фільтр за наявністю на складі
      - name: price_min
        in: query
        type: number
        description: Мінімальна ціна (>= 0)
      - name: price_max
        in: query
        type: number
        description: Максимальна ціна (>= 0)
      - name: sort
        in: query
        type: string
        enum: ["id", "price_asc", "price_desc", "name"]
        default: "id"
        description: Спосіб сортування
      - name: page
        in: query
        type: integer
        default: 1
        description: Номер сторінки (>= 1)
      - name: per_page
        in: query
        type: integer
        default: 20
        description: Кількість записів на сторінці (1..100)
    responses:
      200:
        description: Відфільтрований список товарів та метадані пагінації
        schema:
          type: object
          properties:
            api_version:
              type: string
              example: "v2"
            items:
              type: array
              items:
                $ref: '#/definitions/Product'
            pagination:
              $ref: '#/definitions/PaginationMeta'
      400:
        description: Некоректні параметри фільтрації або пагінації
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    page, per_page, query_errors = parse_pagination_params()
    category_id = _parse_optional_int("category_id", query_errors)
    price_min = _parse_optional_float("price_min", query_errors)
    price_max = _parse_optional_float("price_max", query_errors)

    if price_min is not None and price_max is not None and price_min > price_max:
        query_errors["price_min"] = "Параметр price_min не може перевищувати price_max."

    in_stock_raw = request.args.get("in_stock", "").strip().lower()
    if in_stock_raw and in_stock_raw not in ("true", "false"):
        query_errors["in_stock"] = "Параметр in_stock має бути 'true' або 'false'."

    sort = request.args.get("sort", "id").strip()
    if sort not in ("id", "price_asc", "price_desc", "name"):
        query_errors["sort"] = "Параметр sort має бути одним із: id, price_asc, price_desc, name."

    if query_errors:
        return v2_error_response("Некоректні параметри запиту.", 400, "INVALID_QUERY", query_errors)

    query = request.args.get("q", "").strip().casefold()
    weapon = request.args.get("weapon", "").strip()
    quality = request.args.get("quality", "").strip()
    category_ids = _collect_category_subtree(category_id) if category_id is not None else None

    products = [
        dict(row)
        for row in models.get_products()
        if (not query or query in f"{row['weapon']} {row['skin']} {row['quality']}".casefold())
        and (not weapon or row["weapon"] == weapon)
        and (not quality or row["quality"] == quality)
        and (category_ids is None or row["category_id"] in category_ids)
        and (not in_stock_raw or (row["stock"] > 0) == (in_stock_raw == "true"))
        and (price_min is None or row["price"] >= price_min)
        and (price_max is None or row["price"] <= price_max)
    ]

    if sort == "price_asc":
        products.sort(key=lambda p: (p["price"], p["id"]))
    elif sort == "price_desc":
        products.sort(key=lambda p: (-p["price"], p["id"]))
    elif sort == "name":
        products.sort(key=lambda p: (p["weapon"].casefold(), p["skin"].casefold(), p["id"]))

    page_items, pagination = paginate(products, page, per_page)
    return jsonify({"api_version": "v2", "items": page_items, "pagination": pagination}), 200


@api_v2_bp.route("/products/<int:product_id>", methods=["GET"])
def get_product(product_id):
    """Отримати товар за ідентифікатором (v2)
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
        example: 1
    responses:
      200:
        description: Дані товару
        schema:
          $ref: '#/definitions/Product'
      404:
        description: Товар не знайдено
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    product = models.get_product(product_id)
    if product is None:
        return v2_error_response("Товар не знайдено.", 404)
    return jsonify(dict(product)), 200


@api_v2_bp.route("/products", methods=["POST"])
def create_product():
    """Створити новий товар (v2)
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
        schema:
          $ref: '#/definitions/ProductInput'
    responses:
      201:
        description: Товар створено
        headers:
          Location:
            type: string
        schema:
          $ref: '#/definitions/Product'
      400:
        description: Некоректний JSON
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      415:
        description: Очікується Content-Type application/json
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      422:
        description: Помилка валідації полів
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    data, err = parse_json_object(v2=True)
    if err is not None:
        return err

    parsed, errors = validate_product_payload(data, partial=False, strict_url=True)
    if errors:
        return _validation_error(errors)

    product_id = _save_product_fields(None, parsed)
    created = dict(models.get_product(product_id))
    return jsonify(created), 201, {"Location": url_for("api_v2.get_product", product_id=product_id)}


@api_v2_bp.route("/products/<int:product_id>", methods=["PUT"])
def update_product(product_id):
    """Повністю оновити товар (v2)
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
        example: 1
      - name: body
        in: body
        required: true
        schema:
          $ref: '#/definitions/ProductInput'
    responses:
      200:
        description: Товар оновлено
        schema:
          $ref: '#/definitions/Product'
      400:
        description: Некоректний JSON
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      404:
        description: Товар не знайдено
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      415:
        description: Очікується Content-Type application/json
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      422:
        description: Помилка валідації полів
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    if models.get_product(product_id) is None:
        return v2_error_response("Товар не знайдено.", 404)

    data, err = parse_json_object(v2=True)
    if err is not None:
        return err

    parsed, errors = validate_product_payload(data, partial=False, strict_url=True)
    if errors:
        return _validation_error(errors)

    _save_product_fields(product_id, parsed)
    return jsonify(dict(models.get_product(product_id))), 200


@api_v2_bp.route("/products/<int:product_id>", methods=["PATCH"])
def patch_product(product_id):
    """Частково оновити товар (наприклад, тільки ціну або залишок)
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
        example: 1
      - name: body
        in: body
        required: true
        schema:
          $ref: '#/definitions/ProductPatchInput'
    responses:
      200:
        description: Товар частково оновлено
        schema:
          $ref: '#/definitions/Product'
      400:
        description: Некоректний JSON
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      404:
        description: Товар не знайдено
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      415:
        description: Очікується Content-Type application/json
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      422:
        description: Помилка валідації переданих полів
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    existing = models.get_product(product_id)
    if existing is None:
        return v2_error_response("Товар не знайдено.", 404)

    data, err = parse_json_object(v2=True)
    if err is not None:
        return err

    parsed, errors = validate_product_payload(data, partial=True, strict_url=True)
    if errors:
        return _validation_error(errors)

    merged = {
        "weapon": existing["weapon"],
        "skin": existing["skin"],
        "quality": existing["quality"],
        "price": existing["price"],
        "image_url": existing["image_url"],
        "stock": existing["stock"],
        "category_id": existing["category_id"],
        **parsed,
    }
    _save_product_fields(product_id, merged)
    return jsonify(dict(models.get_product(product_id))), 200


@api_v2_bp.route("/products/<int:product_id>", methods=["DELETE"])
def delete_product(product_id):
    """Видалити товар (v2)
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
    responses:
      204:
        description: Товар видалено
      404:
        description: Товар не знайдено
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      409:
        description: Товар входить до існуючих замовлень
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    if models.get_product(product_id) is None:
        return v2_error_response("Товар не знайдено.", 404)
    if not models.delete_product(product_id):
        return v2_error_response("Не можна видалити товар, який входить до замовлень.", 409)
    return "", 204


# ------------------------------------------------------------------- Categories


@api_v2_bp.route("/categories", methods=["GET"])
def get_categories():
    """Отримати список усіх категорій (v2)
    ---
    tags:
      - Categories
    produces:
      - application/json
    responses:
      200:
        description: Перелік категорій каталогу
        schema:
          type: object
          properties:
            api_version:
              type: string
              example: "v2"
            items:
              type: array
              items:
                $ref: '#/definitions/Category'
            total:
              type: integer
              example: 6
    """
    items = models.get_categories()
    return jsonify({"api_version": "v2", "items": items, "total": len(items)}), 200


@api_v2_bp.route("/categories/<int:category_id>", methods=["GET"])
def get_category(category_id):
    """Отримати категорію за ідентифікатором
    ---
    tags:
      - Categories
    produces:
      - application/json
    parameters:
      - name: category_id
        in: path
        type: integer
        required: true
        example: 1
    responses:
      200:
        description: Дані категорії
        schema:
          $ref: '#/definitions/Category'
      404:
        description: Категорію не знайдено
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    category = models.get_category(category_id)
    if category is None:
        return v2_error_response("Категорію не знайдено.", 404)
    return jsonify(category), 200


@api_v2_bp.route("/categories", methods=["POST"])
def create_category():
    """Створити нову категорію
    ---
    tags:
      - Categories
    consumes:
      - application/json
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          $ref: '#/definitions/CategoryInput'
    responses:
      201:
        description: Категорію створено
        headers:
          Location:
            type: string
        schema:
          $ref: '#/definitions/Category'
      409:
        description: Категорія з такою назвою вже існує на цьому рівні
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      422:
        description: Помилка валідації або батьківську категорію не знайдено
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    data, err = parse_json_object(v2=True)
    if err is not None:
        return err

    parsed, errors = validate_category_payload(data)
    if errors:
        return _validation_error(errors)

    try:
        category_id = models.save_category(None, parsed["name"], parsed["parent_id"])
    except ValueError as error:
        msg = str(error)
        if "вже є" in msg:
            return v2_error_response(msg, 409)
        return v2_error_response(msg, 422, "VALIDATION_ERROR")

    return (
        jsonify(models.get_category(category_id)),
        201,
        {"Location": url_for("api_v2.get_category", category_id=category_id)},
    )


@api_v2_bp.route("/categories/<int:category_id>", methods=["PUT"])
def update_category(category_id):
    """Оновити категорію за ідентифікатором
    ---
    tags:
      - Categories
    consumes:
      - application/json
    produces:
      - application/json
    parameters:
      - name: category_id
        in: path
        type: integer
        required: true
      - name: body
        in: body
        required: true
        schema:
          $ref: '#/definitions/CategoryInput'
    responses:
      200:
        description: Категорію оновлено
        schema:
          $ref: '#/definitions/Category'
      404:
        description: Категорію не знайдено
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      409:
        description: Конфлікт ієрархії або дублікат назви
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      422:
        description: Помилка валідації
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    if models.get_category(category_id) is None:
        return v2_error_response("Категорію не знайдено.", 404)

    data, err = parse_json_object(v2=True)
    if err is not None:
        return err

    parsed, errors = validate_category_payload(data)
    if errors:
        return _validation_error(errors)

    try:
        models.save_category(category_id, parsed["name"], parsed["parent_id"])
    except ValueError as error:
        msg = str(error)
        if "вже є" in msg or "підкатегорії" in msg or "самої себе" in msg:
            return v2_error_response(msg, 409)
        return v2_error_response(msg, 422, "VALIDATION_ERROR")

    return jsonify(models.get_category(category_id)), 200


@api_v2_bp.route("/categories/<int:category_id>", methods=["DELETE"])
def delete_category(category_id):
    """Видалити категорію (підкатегорії й товари переносяться на батьківський рівень)
    ---
    tags:
      - Categories
    produces:
      - application/json
    parameters:
      - name: category_id
        in: path
        type: integer
        required: true
    responses:
      204:
        description: Категорію видалено
      404:
        description: Категорію не знайдено
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    if not models.delete_category(category_id):
        return v2_error_response("Категорію не знайдено.", 404)
    return "", 204


# ----------------------------------------------------------------------- Orders


@api_v2_bp.route("/orders", methods=["GET"])
def get_orders():
    """Отримати список замовлень із фільтрацією та пагінацією (v2)
    ---
    tags:
      - Orders
    produces:
      - application/json
    parameters:
      - name: status
        in: query
        type: string
        enum: ["pending", "processing", "shipped", "completed", "cancelled"]
        description: Фільтр за статусом замовлення
      - name: user_id
        in: query
        type: integer
        description: Фільтр за ідентифікатором користувача
      - name: page
        in: query
        type: integer
        default: 1
      - name: per_page
        in: query
        type: integer
        default: 20
    responses:
      200:
        description: Список замовлень та метадані пагінації
        schema:
          type: object
          properties:
            api_version:
              type: string
              example: "v2"
            items:
              type: array
              items:
                $ref: '#/definitions/OrderSummary'
            pagination:
              $ref: '#/definitions/PaginationMeta'
      400:
        description: Некоректні параметри запиту
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    page, per_page, query_errors = parse_pagination_params()
    user_id = _parse_optional_int("user_id", query_errors)
    status = request.args.get("status", "").strip()
    if status and status not in models.ORDER_STATUSES:
        query_errors["status"] = f"Статус має бути одним із: {', '.join(models.ORDER_STATUSES)}."

    if query_errors:
        return v2_error_response("Некоректні параметри запиту.", 400, "INVALID_QUERY", query_errors)

    orders = [
        dict(row)
        for row in models.get_orders()
        if (not status or row["status"] == status) and (user_id is None or row["user_id"] == user_id)
    ]
    page_items, pagination = paginate(orders, page, per_page)
    return jsonify({"api_version": "v2", "items": page_items, "pagination": pagination}), 200


@api_v2_bp.route("/orders/<int:order_id>", methods=["GET"])
def get_order(order_id):
    """Отримати замовлення за ідентифікатором (v2)
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
        example: 1
    responses:
      200:
        description: Деталі замовлення
        schema:
          $ref: '#/definitions/OrderDetail'
      404:
        description: Замовлення не знайдено
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    order = models.get_order(order_id)
    if order is None:
        return v2_error_response("Замовлення не знайдено.", 404)
    return jsonify(order), 200


@api_v2_bp.route("/orders", methods=["POST"])
def create_order():
    """Створити нове замовлення (v2)
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
        schema:
          $ref: '#/definitions/OrderCreateInput'
    responses:
      201:
        description: Замовлення створено
        headers:
          Location:
            type: string
        schema:
          $ref: '#/definitions/OrderDetail'
      404:
        description: Товар не знайдено
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      409:
        description: Недостатньо товару на складі
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      422:
        description: Помилка валідації полів або недійсний промокод
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    data, err = parse_json_object(v2=True)
    if err is not None:
        return err

    parsed, errors = validate_order_payload(data)
    if errors:
        return _validation_error(errors)

    if models.get_product(parsed["product_id"]) is None:
        return v2_error_response("Товар не знайдено.", 404)

    try:
        order_id = models.create_order(**parsed)
    except ValueError as error:
        msg = str(error)
        if "складі" in msg:
            return v2_error_response(msg, 409, "INSUFFICIENT_STOCK")
        return v2_error_response(msg, 422, "VALIDATION_ERROR")

    created = models.get_order(order_id)
    return jsonify(created), 201, {"Location": url_for("api_v2.get_order", order_id=order_id)}


@api_v2_bp.route("/orders/<int:order_id>", methods=["PATCH"])
def update_order_status(order_id):
    """Оновити статус замовлення (v2)
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
      - name: body
        in: body
        required: true
        schema:
          $ref: '#/definitions/OrderStatusInput'
    responses:
      200:
        description: Статус замовлення оновлено
        schema:
          $ref: '#/definitions/OrderDetail'
      404:
        description: Замовлення не знайдено
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      409:
        description: Недостатньо товару на складі для відновлення скасованого замовлення
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      422:
        description: Недопустимий статус
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    if models.get_order(order_id) is None:
        return v2_error_response("Замовлення не знайдено.", 404)

    data, err = parse_json_object(v2=True)
    if err is not None:
        return err

    status = data.get("status")
    if not isinstance(status, str) or status not in models.ORDER_STATUSES:
        allowed = ", ".join(models.ORDER_STATUSES)
        return _validation_error({"status": f"Поле status має бути одним із: {allowed}."})

    try:
        models.update_order_status(order_id, status)
    except ValueError as error:
        return v2_error_response(str(error), 409, "INSUFFICIENT_STOCK")

    return jsonify(models.get_order(order_id)), 200


@api_v2_bp.route("/orders/<int:order_id>", methods=["DELETE"])
def delete_order(order_id):
    """Видалити замовлення (v2)
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
    responses:
      204:
        description: Замовлення видалено
      404:
        description: Замовлення не знайдено
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    if not models.delete_order(order_id):
        return v2_error_response("Замовлення не знайдено.", 404)
    return "", 204


# ------------------------------------------------------------------- Promocodes


@api_v2_bp.route("/promocodes", methods=["GET"])
def get_promocodes():
    """Отримати список промокодів
    ---
    tags:
      - Promocodes
    produces:
      - application/json
    parameters:
      - name: available
        in: query
        type: string
        enum: ["true", "false"]
        description: Якщо true — повернути лише активні й дійсні промокоди
    responses:
      200:
        description: Список промокодів
        schema:
          type: object
          properties:
            api_version:
              type: string
              example: "v2"
            items:
              type: array
              items:
                $ref: '#/definitions/Promocode'
            total:
              type: integer
      400:
        description: Некоректний параметр available
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    available_raw = request.args.get("available", "").strip().lower()
    if available_raw and available_raw not in ("true", "false"):
        return v2_error_response(
            "Некоректні параметри запиту.",
            400,
            "INVALID_QUERY",
            {"available": "Параметр available має бути 'true' або 'false'."},
        )

    if available_raw == "true":
        items = models.get_available_promocodes()
    elif available_raw == "false":
        available_ids = {p["id"] for p in models.get_available_promocodes()}
        items = [dict(row) for row in models.get_promocodes() if row["id"] not in available_ids]
    else:
        items = [dict(row) for row in models.get_promocodes()]

    return jsonify({"api_version": "v2", "items": items, "total": len(items)}), 200


@api_v2_bp.route("/promocodes/<int:promo_id>", methods=["GET"])
def get_promocode(promo_id):
    """Отримати промокод за ідентифікатором
    ---
    tags:
      - Promocodes
    produces:
      - application/json
    parameters:
      - name: promo_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Дані промокоду
        schema:
          $ref: '#/definitions/Promocode'
      404:
        description: Промокод не знайдено
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    promo = models.get_promocode(promo_id)
    if promo is None:
        return v2_error_response("Промокод не знайдено.", 404)
    return jsonify(dict(promo)), 200


@api_v2_bp.route("/promocodes", methods=["POST"])
def create_promocode():
    """Створити новий промокод
    ---
    tags:
      - Promocodes
    consumes:
      - application/json
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          $ref: '#/definitions/PromocodeInput'
    responses:
      201:
        description: Промокод створено
        headers:
          Location:
            type: string
        schema:
          $ref: '#/definitions/Promocode'
      409:
        description: Промокод із таким кодом уже існує
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      422:
        description: Помилка валідації полів
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    data, err = parse_json_object(v2=True)
    if err is not None:
        return err

    parsed, errors = validate_promocode_payload(data)
    if errors:
        return _validation_error(errors)

    try:
        promo_id = models.save_promocode(None, **parsed)
    except ValueError as error:
        msg = str(error)
        if "уже існує" in msg:
            return v2_error_response(msg, 409)
        return v2_error_response(msg, 422, "VALIDATION_ERROR")

    return (
        jsonify(dict(models.get_promocode(promo_id))),
        201,
        {"Location": url_for("api_v2.get_promocode", promo_id=promo_id)},
    )


@api_v2_bp.route("/promocodes/<int:promo_id>", methods=["PUT"])
def update_promocode(promo_id):
    """Оновити існуючий промокод
    ---
    tags:
      - Promocodes
    consumes:
      - application/json
    produces:
      - application/json
    parameters:
      - name: promo_id
        in: path
        type: integer
        required: true
      - name: body
        in: body
        required: true
        schema:
          $ref: '#/definitions/PromocodeInput'
    responses:
      200:
        description: Промокод оновлено
        schema:
          $ref: '#/definitions/Promocode'
      404:
        description: Промокод не знайдено
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      409:
        description: Промокод із таким кодом уже існує
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      422:
        description: Помилка валідації полів
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    if models.get_promocode(promo_id) is None:
        return v2_error_response("Промокод не знайдено.", 404)

    data, err = parse_json_object(v2=True)
    if err is not None:
        return err

    parsed, errors = validate_promocode_payload(data)
    if errors:
        return _validation_error(errors)

    try:
        models.save_promocode(promo_id, **parsed)
    except ValueError as error:
        msg = str(error)
        if "уже існує" in msg:
            return v2_error_response(msg, 409)
        return v2_error_response(msg, 422, "VALIDATION_ERROR")

    return jsonify(dict(models.get_promocode(promo_id))), 200


@api_v2_bp.route("/promocodes/<int:promo_id>", methods=["DELETE"])
def delete_promocode(promo_id):
    """Видалити промокод
    ---
    tags:
      - Promocodes
    produces:
      - application/json
    parameters:
      - name: promo_id
        in: path
        type: integer
        required: true
    responses:
      204:
        description: Промокод видалено
      404:
        description: Промокод не знайдено
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    if not models.delete_promocode(promo_id):
        return v2_error_response("Промокод не знайдено.", 404)
    return "", 204


# ------------------------------------------------------------------------ Users


@api_v2_bp.route("/users", methods=["GET"])
def get_users():
    """Отримати список користувачів (без паролів) із фільтрацією й пагінацією
    ---
    tags:
      - Users
    produces:
      - application/json
    parameters:
      - name: role
        in: query
        type: string
        enum: ["admin", "customer"]
        description: Фільтр за роллю
      - name: page
        in: query
        type: integer
        default: 1
      - name: per_page
        in: query
        type: integer
        default: 20
    responses:
      200:
        description: Список користувачів та пагінація
        schema:
          type: object
          properties:
            api_version:
              type: string
              example: "v2"
            items:
              type: array
              items:
                $ref: '#/definitions/User'
            pagination:
              $ref: '#/definitions/PaginationMeta'
      400:
        description: Некоректні параметри запиту
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    page, per_page, query_errors = parse_pagination_params()
    role = request.args.get("role", "").strip()
    if role and role not in ("admin", "customer"):
        query_errors["role"] = "Параметр role має бути 'admin' або 'customer'."
    if query_errors:
        return v2_error_response("Некоректні параметри запиту.", 400, "INVALID_QUERY", query_errors)

    users = [u for u in models.get_users() if not role or u["role"] == role]
    page_items, pagination = paginate(users, page, per_page)
    return jsonify({"api_version": "v2", "items": page_items, "pagination": pagination}), 200


@api_v2_bp.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    """Отримати користувача за ідентифікатором
    ---
    tags:
      - Users
    produces:
      - application/json
    parameters:
      - name: user_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Профіль користувача та його замовлення
        schema:
          $ref: '#/definitions/User'
      404:
        description: Користувача не знайдено
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    user = models.get_user(user_id)
    if user is None:
        return v2_error_response("Користувача не знайдено.", 404)
    return jsonify(user), 200


@api_v2_bp.route("/users", methods=["POST"])
def create_user():
    """Створити обліковий запис клієнта
    ---
    tags:
      - Users
    consumes:
      - application/json
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          $ref: '#/definitions/UserCreateInput'
    responses:
      201:
        description: Користувача створено
        headers:
          Location:
            type: string
        schema:
          $ref: '#/definitions/User'
      409:
        description: Користувач із таким email уже існує
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      422:
        description: Помилка валідації полів
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    data, err = parse_json_object(v2=True)
    if err is not None:
        return err

    parsed, errors = validate_user_create_payload(data)
    if errors:
        return _validation_error(errors)

    try:
        user_id = models.create_account(parsed["name"], parsed["email"], parsed["password"])
    except ValueError as error:
        return v2_error_response(str(error), 409)

    return jsonify(models.get_user(user_id)), 201, {"Location": url_for("api_v2.get_user", user_id=user_id)}


@api_v2_bp.route("/users/<int:user_id>", methods=["PATCH"])
def update_user(user_id):
    """Частково оновити дані або роль користувача
    ---
    tags:
      - Users
    consumes:
      - application/json
    produces:
      - application/json
    parameters:
      - name: user_id
        in: path
        type: integer
        required: true
      - name: body
        in: body
        required: true
        schema:
          $ref: '#/definitions/UserUpdateInput'
    responses:
      200:
        description: Дані користувача оновлено
        schema:
          $ref: '#/definitions/User'
      404:
        description: Користувача не знайдено
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      409:
        description: Конфлікт email або спроба зняти роль останнього адміністратора
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      422:
        description: Помилка валідації полів
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    existing = models.get_user(user_id)
    if existing is None:
        return v2_error_response("Користувача не знайдено.", 404)

    data, err = parse_json_object(v2=True)
    if err is not None:
        return err

    parsed, errors = validate_user_update_payload(data, existing)
    if errors:
        return _validation_error(errors)

    try:
        models.save_user(user_id, parsed["name"], parsed["email"], parsed["role"])
    except ValueError as error:
        msg = str(error)
        if "не має пароля" in msg:
            return v2_error_response(msg, 422, "VALIDATION_ERROR")
        return v2_error_response(msg, 409)

    return jsonify(models.get_user(user_id)), 200


@api_v2_bp.route("/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    """Видалити користувача та його замовлення
    ---
    tags:
      - Users
    produces:
      - application/json
    parameters:
      - name: user_id
        in: path
        type: integer
        required: true
    responses:
      204:
        description: Користувача видалено
      404:
        description: Користувача не знайдено
        schema:
          $ref: '#/definitions/V2ErrorResponse'
      409:
        description: Неможливо видалити останнього адміністратора
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    try:
        deleted = models.delete_user(user_id)
    except ValueError as error:
        return v2_error_response(str(error), 409)

    if not deleted:
        return v2_error_response("Користувача не знайдено.", 404)
    return "", 204


# --------------------------------------------------------------------- Feedback


@api_v2_bp.route("/feedback", methods=["GET"])
def get_feedback():
    """Отримати список відгуків із пагінацією (v2)
    ---
    tags:
      - Feedback
    produces:
      - application/json
    parameters:
      - name: page
        in: query
        type: integer
        default: 1
      - name: per_page
        in: query
        type: integer
        default: 20
    responses:
      200:
        description: Список відгуків та метадані пагінації
        schema:
          type: object
          properties:
            api_version:
              type: string
              example: "v2"
            items:
              type: array
              items:
                $ref: '#/definitions/Feedback'
            pagination:
              $ref: '#/definitions/PaginationMeta'
      400:
        description: Некоректні параметри пагінації
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    page, per_page, query_errors = parse_pagination_params()
    if query_errors:
        return v2_error_response("Некоректні параметри запиту.", 400, "INVALID_QUERY", query_errors)

    entries = [dict(row) for row in models.get_all_feedback()]
    page_items, pagination = paginate(entries, page, per_page)
    return jsonify({"api_version": "v2", "items": page_items, "pagination": pagination}), 200


@api_v2_bp.route("/feedback/<int:feedback_id>", methods=["GET"])
def get_feedback_item(feedback_id):
    """Отримати один відгук за ідентифікатором
    ---
    tags:
      - Feedback
    produces:
      - application/json
    parameters:
      - name: feedback_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Дані відгуку
        schema:
          $ref: '#/definitions/Feedback'
      404:
        description: Відгук не знайдено
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    entry = models.get_feedback(feedback_id)
    if entry is None:
        return v2_error_response("Відгук не знайдено.", 404)
    return jsonify(dict(entry)), 200


@api_v2_bp.route("/feedback", methods=["POST"])
def create_feedback():
    """Створити новий відгук (v2)
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
        schema:
          $ref: '#/definitions/FeedbackInput'
    responses:
      201:
        description: Відгук збережено
        headers:
          Location:
            type: string
        schema:
          $ref: '#/definitions/Feedback'
      422:
        description: Помилка валідації полів
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    data, err = parse_json_object(v2=True)
    if err is not None:
        return err

    parsed, errors = validate_feedback_payload(data)
    if errors:
        return _validation_error(errors)

    feedback_id = models.create_feedback(parsed["name"], parsed["email"], parsed["message"])
    created = dict(models.get_feedback(feedback_id))
    return (
        jsonify(created),
        201,
        {"Location": url_for("api_v2.get_feedback_item", feedback_id=feedback_id)},
    )


@api_v2_bp.route("/feedback/<int:feedback_id>", methods=["DELETE"])
def delete_feedback(feedback_id):
    """Видалити відгук за ідентифікатором
    ---
    tags:
      - Feedback
    produces:
      - application/json
    parameters:
      - name: feedback_id
        in: path
        type: integer
        required: true
    responses:
      204:
        description: Відгук видалено
      404:
        description: Відгук не знайдено
        schema:
          $ref: '#/definitions/V2ErrorResponse'
    """
    if not models.delete_feedback(feedback_id):
        return v2_error_response("Відгук не знайдено.", 404)
    return "", 204
