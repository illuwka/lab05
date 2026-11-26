"""CRUD-операції для промокодів та замовлень."""
import re
import sqlite3
from datetime import date

from .catalog import get_product
from .db import get_db

ORDER_STATUSES = ("pending", "processing", "shipped", "completed", "cancelled")
STATUS_LABELS = {
    "pending": "Нове",
    "processing": "В обробці",
    "shipped": "Відправлено",
    "completed": "Завершено",
    "cancelled": "Скасовано",
}


def get_promocodes():
    return get_db().execute("""
        SELECT p.id, p.code, p.discount_percent, p.active, p.expires_on, p.usage_limit,
               p.created_at,
               (SELECT COUNT(*) FROM orders o
                WHERE o.promo_code = p.code AND o.status != 'cancelled') AS used_count
        FROM promocodes p
        ORDER BY p.id DESC
    """).fetchall()


def get_available_promocodes():
    today = date.today().isoformat()
    return [
        dict(promo)
        for promo in get_promocodes()
        if promo["active"]
        and (not promo["expires_on"] or promo["expires_on"] >= today)
        and (promo["usage_limit"] is None or promo["used_count"] < promo["usage_limit"])
    ]


def save_promocode(promo_id, code, discount_percent, expires_on=None, usage_limit=None, active=True):
    code = code.strip().upper()
    if not re.fullmatch(r"[A-Z0-9_-]{3,32}", code):
        raise ValueError("Код має містити 3–32 латинські літери, цифри, дефіс або підкреслення.")
    try:
        discount_percent = int(discount_percent)
        if not 1 <= discount_percent <= 100:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("Знижка має бути цілим числом від 1 до 100 відсотків.")
    expires_on = (expires_on or "").strip() or None
    if expires_on:
        try:
            date.fromisoformat(expires_on)
        except ValueError as error:
            raise ValueError("Вкажіть коректну дату завершення промокоду.") from error
    if usage_limit in (None, ""):
        usage_limit = None
    else:
        try:
            usage_limit = int(usage_limit)
            if usage_limit < 1:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError("Ліміт використань має бути додатним цілим числом.")

    db = get_db()
    values = (code, discount_percent, int(bool(active)), expires_on, usage_limit)
    try:
        if promo_id is None:
            cursor = db.execute(
                "INSERT INTO promocodes (code, discount_percent, active, expires_on, usage_limit) VALUES (?, ?, ?, ?, ?)",
                values,
            )
            promo_id = cursor.lastrowid
        else:
            cursor = db.execute(
                "UPDATE promocodes SET code=?, discount_percent=?, active=?, expires_on=?, usage_limit=? WHERE id=?",
                (*values, promo_id),
            )
            if cursor.rowcount == 0:
                raise ValueError("Промокод не знайдено.")
        db.commit()
        return promo_id
    except sqlite3.IntegrityError as error:
        db.rollback()
        raise ValueError("Промокод із таким кодом уже існує.") from error
    except Exception:
        db.rollback()
        raise


def delete_promocode(promo_id):
    db = get_db()
    cursor = db.execute("DELETE FROM promocodes WHERE id = ?", (promo_id,))
    db.commit()
    return cursor.rowcount > 0


def _promo_discount(db, code, subtotal):
    code = (code or "").strip().upper()
    if not code:
        return None, 0.0
    promo = db.execute("""
        SELECT id, code, discount_percent, active, expires_on, usage_limit
        FROM promocodes WHERE code = ? COLLATE NOCASE
    """, (code,)).fetchone()
    if promo is None or not promo["active"]:
        raise ValueError("Промокод недійсний або вимкнений.")
    if promo["expires_on"] and promo["expires_on"] < date.today().isoformat():
        raise ValueError("Термін дії промокоду завершився.")
    if promo["usage_limit"] is not None:
        used = db.execute(
            "SELECT COUNT(*) FROM orders WHERE promo_code = ? AND status != 'cancelled'",
            (promo["code"],),
        ).fetchone()[0]
        if used >= promo["usage_limit"]:
            raise ValueError("Ліміт використань цього промокоду вичерпано.")
    return promo["code"], round(subtotal * promo["discount_percent"] / 100, 2)


def get_user_orders(user_id):
    db = get_db()
    rows = db.execute("""
        SELECT o.id, o.user_id, o.customer_name, o.customer_email, o.total_price,
               o.promo_code, o.discount_amount, o.status, o.created_at
        FROM orders o
        WHERE o.user_id = ?
        ORDER BY o.created_at DESC, o.id DESC
    """, (user_id,)).fetchall()
    orders = []
    for r in rows:
        order = dict(r)
        items = db.execute("""
            SELECT oi.id, oi.product_id, oi.product_name, oi.unit_price, oi.quantity,
                   p.weapon, p.skin
            FROM order_items oi
            LEFT JOIN products p ON p.id = oi.product_id
            WHERE oi.order_id = ?
        """, (order["id"],)).fetchall()
        order["items_list"] = [dict(it) for it in items]
        order["items_text"] = ", ".join(f"{it['product_name']} × {it['quantity']}" for it in items) if items else "—"
        orders.append(order)
    return orders


def create_order(product_id, customer_name, customer_email, quantity, user_id=None, status="pending", promo_code=""):
    if status not in ORDER_STATUSES:
        raise ValueError("Недопустимий статус замовлення.")
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    try:
        product = get_product(product_id)
        if product is None:
            raise ValueError("Товар не знайдено.")
        if quantity < 1:
            raise ValueError("Кількість має бути не меншою за 1.")
        if status != "cancelled" and quantity > product["stock"]:
            raise ValueError("Недостатньо товару на складі.")

        if user_id is not None:
            user = db.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,)).fetchone()
            if user:
                customer_name = user["name"]
                customer_email = user["email"]
        else:
            customer_email = customer_email.strip()
            customer_name = customer_name.strip()
            user = db.execute("SELECT id, name, email FROM users WHERE email = ?", (customer_email,)).fetchone()
            if user is None:
                cur_u = db.execute("INSERT INTO users (name, email) VALUES (?, ?)", (customer_name, customer_email))
                user_id = cur_u.lastrowid
            else:
                user_id = user["id"]

        subtotal = round(product["price"] * quantity, 2)
        applied_promo, discount_amount = _promo_discount(db, promo_code, subtotal)
        total = round(subtotal - discount_amount, 2)
        cursor = db.execute(
            "INSERT INTO orders (user_id, customer_name, customer_email, total_price, promo_code, discount_amount, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, customer_name.strip(), customer_email.strip(), total, applied_promo, discount_amount, status),
        )
        order_id = cursor.lastrowid
        db.execute(
            "INSERT INTO order_items (order_id, product_id, product_name, unit_price, quantity) VALUES (?, ?, ?, ?, ?)",
            (order_id, product_id, f'{product["weapon"]} | {product["skin"]}', product["price"], quantity),
        )
        if status != "cancelled":
            db.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (quantity, product_id))
        db.commit()
        return order_id
    except Exception:
        db.rollback()
        raise


def update_order(order_id, product_id=None, quantity=None, total_price=None, status=None, user_id=None):
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    try:
        order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if order is None:
            raise ValueError("Замовлення не знайдено.")

        old_status = order["status"]
        new_status = status if status in ORDER_STATUSES else old_status

        current_item = db.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchone()

        if product_id is not None and quantity is not None:
            quantity = int(quantity)
            if quantity < 1:
                raise ValueError("Кількість має бути не меншою за 1.")
            product = get_product(product_id)
            if product is None:
                raise ValueError("Товар не знайдено.")

            if current_item and old_status != "cancelled":
                db.execute(
                    "UPDATE products SET stock = stock + ? WHERE id = ?",
                    (current_item["quantity"], current_item["product_id"]),
                )

            if new_status != "cancelled":
                cur_stock = db.execute("SELECT stock FROM products WHERE id = ?", (product_id,)).fetchone()["stock"]
                if cur_stock < quantity:
                    raise ValueError(f"Недостатньо товару на складі (залишок: {cur_stock}).")
                db.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (quantity, product_id))

            if current_item:
                db.execute("""
                    UPDATE order_items
                    SET product_id = ?, product_name = ?, unit_price = ?, quantity = ?
                    WHERE id = ?
                """, (product_id, f"{product['weapon']} | {product['skin']}", product["price"], quantity, current_item["id"]))
            else:
                db.execute("""
                    INSERT INTO order_items (order_id, product_id, product_name, unit_price, quantity)
                    VALUES (?, ?, ?, ?, ?)
                """, (order_id, product_id, f"{product['weapon']} | {product['skin']}", product["price"], quantity))

            if total_price is None or total_price < 0:
                total_price = round(product["price"] * quantity, 2)
        else:
            if old_status != "cancelled" and new_status == "cancelled":
                items = db.execute("SELECT product_id, quantity FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
                for item in items:
                    db.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (item["quantity"], item["product_id"]))
            elif old_status == "cancelled" and new_status != "cancelled":
                items = db.execute("SELECT product_id, quantity FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
                for item in items:
                    changed = db.execute(
                        "UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= ?",
                        (item["quantity"], item["product_id"], item["quantity"]),
                    )
                    if changed.rowcount == 0:
                        raise ValueError("Недостатньо товару на складі, щоб відновити це замовлення.")

        if total_price is None:
            total_price = order["total_price"]

        target_user_id = user_id if user_id is not None else order["user_id"]
        if target_user_id:
            u = db.execute("SELECT name, email FROM users WHERE id = ?", (target_user_id,)).fetchone()
            if u:
                c_name = u["name"]
                c_email = u["email"]
            else:
                c_name = order["customer_name"]
                c_email = order["customer_email"]
        else:
            c_name = order["customer_name"]
            c_email = order["customer_email"]

        db.execute("""
            UPDATE orders
            SET user_id = ?, customer_name = ?, customer_email = ?, total_price = ?, status = ?
            WHERE id = ?
        """, (target_user_id, c_name, c_email, total_price, new_status, order_id))

        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def delete_order(order_id):
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    try:
        order = db.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
        if order is None:
            db.rollback()
            return False
        if order["status"] != "cancelled":
            items = db.execute("SELECT product_id, quantity FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
            for item in items:
                db.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (item["quantity"], item["product_id"]))
        db.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
        db.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def get_orders():
    return get_db().execute("""
        SELECT o.id, o.user_id, o.customer_name, o.customer_email, o.total_price,
               o.promo_code, o.discount_amount, o.status, o.created_at,
               GROUP_CONCAT(oi.product_name || ' × ' || oi.quantity, ', ') AS items
        FROM orders o
        LEFT JOIN order_items oi ON oi.order_id = o.id
        GROUP BY o.id
        ORDER BY o.created_at DESC, o.id DESC
    """).fetchall()


def get_order(order_id):
    db = get_db()
    row = db.execute("""
        SELECT o.id, o.user_id, o.customer_name, o.customer_email, o.total_price,
               o.promo_code, o.discount_amount, o.status, o.created_at
        FROM orders o
        WHERE o.id = ?
    """, (order_id,)).fetchone()
    if row is None:
        return None
    order = dict(row)
    items = db.execute("""
        SELECT oi.id, oi.product_id, oi.product_name, oi.unit_price, oi.quantity,
               p.weapon, p.skin
        FROM order_items oi
        LEFT JOIN products p ON p.id = oi.product_id
        WHERE oi.order_id = ?
        ORDER BY oi.id
    """, (order_id,)).fetchall()
    order["items"] = [dict(item) for item in items]
    return order


def update_order_status(order_id, status):
    if status not in ORDER_STATUSES:
        raise ValueError("Недопустимий статус замовлення.")
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    try:
        order = db.execute("SELECT status FROM orders WHERE id=?", (order_id,)).fetchone()
        if order is None:
            db.rollback()
            return False
        old = order["status"]
        items = db.execute("SELECT product_id, quantity FROM order_items WHERE order_id=?", (order_id,)).fetchall()
        if old != "cancelled" and status == "cancelled":
            for item in items:
                db.execute("UPDATE products SET stock=stock+? WHERE id=?", (item["quantity"], item["product_id"]))
        elif old == "cancelled" and status != "cancelled":
            for item in items:
                changed = db.execute(
                    "UPDATE products SET stock=stock-? WHERE id=? AND stock>=?",
                    (item["quantity"], item["product_id"], item["quantity"]),
                )
                if changed.rowcount == 0:
                    raise ValueError("Недостатньо товару на складі, щоб відновити це замовлення.")
        db.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
