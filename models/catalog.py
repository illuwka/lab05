"""CRUD-операції для категорій, товарів та списку обраного."""
from .db import get_db


def get_or_create_category(db, name, parent_id):
    row = db.execute(
        "SELECT id FROM categories WHERE name = ? COLLATE NOCASE AND parent_id IS ?",
        (name, parent_id),
    ).fetchone()
    if row:
        return row["id"]
    cursor = db.execute("INSERT INTO categories (name, parent_id) VALUES (?, ?)", (name, parent_id))
    return cursor.lastrowid


def get_categories():
    rows = [
        dict(row)
        for row in get_db().execute(
            "SELECT id, name, parent_id FROM categories ORDER BY name COLLATE NOCASE, id"
        )
    ]
    by_id = {row["id"]: row for row in rows}
    for row in rows:
        chain, seen, current = [], set(), row
        while current and current["id"] not in seen:
            seen.add(current["id"])
            chain.append(current["name"])
            current = by_id.get(current["parent_id"])
        row["depth"] = len(chain) - 1
        row["path"] = " / ".join(reversed(chain))
    return sorted(rows, key=lambda row: (row["path"].casefold(), row["id"]))


def save_category(category_id, name, parent_id=None):
    db = get_db()
    name = name.strip()
    if not name or len(name) > 80:
        raise ValueError("Назва категорії має містити від 1 до 80 символів.")
    if category_id is not None:
        existing = db.execute("SELECT id FROM categories WHERE id = ?", (category_id,)).fetchone()
        if not existing:
            raise ValueError("Категорію не знайдено.")
        if parent_id == category_id:
            raise ValueError("Категорія не може бути батьківською для самої себе.")
        descendants = {category_id}
        changed = True
        while changed:
            placeholders = ",".join("?" for _ in descendants)
            children = {
                row[0]
                for row in db.execute(
                    f"SELECT id FROM categories WHERE parent_id IN ({placeholders})",
                    tuple(descendants),
                )
            } if descendants else set()
            new_descendants = descendants | children
            changed = new_descendants != descendants
            descendants = new_descendants
        if parent_id in descendants:
            raise ValueError("Не можна перемістити категорію всередину її підкатегорії.")
    if parent_id is not None and not db.execute("SELECT 1 FROM categories WHERE id = ?", (parent_id,)).fetchone():
        raise ValueError("Батьківську категорію не знайдено.")
    duplicate = db.execute(
        "SELECT 1 FROM categories WHERE name = ? COLLATE NOCASE AND parent_id IS ? AND id IS NOT ?",
        (name, parent_id, category_id),
    ).fetchone()
    if duplicate:
        raise ValueError("Категорія з такою назвою вже є на цьому рівні.")
    if category_id is None:
        cursor = db.execute("INSERT INTO categories (name, parent_id) VALUES (?, ?)", (name, parent_id))
        result = cursor.lastrowid
    else:
        db.execute("UPDATE categories SET name = ?, parent_id = ? WHERE id = ?", (name, parent_id, category_id))
        result = category_id
    db.commit()
    return result


def delete_category(category_id):
    db = get_db()
    row = db.execute("SELECT parent_id FROM categories WHERE id = ?", (category_id,)).fetchone()
    if not row:
        return False
    parent_id = row["parent_id"]
    db.execute("UPDATE categories SET parent_id = ? WHERE parent_id = ?", (parent_id, category_id))
    db.execute("UPDATE products SET category_id = ? WHERE category_id = ?", (parent_id, category_id))
    db.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    db.commit()
    return True


def get_products():
    return get_db().execute("""
        SELECT p.id, p.weapon, p.skin, p.quality, p.price, p.image_url, p.stock,
               p.category_id, c.name AS category_name
        FROM products p
        LEFT JOIN categories c ON c.id = p.category_id
        ORDER BY p.id
    """).fetchall()


def get_favorite_product_ids(user_id):
    return {
        row["product_id"]
        for row in get_db().execute("SELECT product_id FROM favorites WHERE user_id = ?", (user_id,))
    }


def get_favorite_products(user_id):
    return get_db().execute("""
        SELECT p.id, p.weapon, p.skin, p.quality, p.price, p.image_url, p.stock,
               p.category_id, c.name AS category_name
        FROM favorites f
        JOIN products p ON p.id = f.product_id
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE f.user_id = ?
        ORDER BY f.created_at DESC, p.id
    """, (user_id,)).fetchall()


def toggle_favorite(user_id, product_id):
    db = get_db()
    existing = db.execute(
        "SELECT 1 FROM favorites WHERE user_id = ? AND product_id = ?",
        (user_id, product_id),
    ).fetchone()
    if existing:
        db.execute("DELETE FROM favorites WHERE user_id = ? AND product_id = ?", (user_id, product_id))
        saved = False
    else:
        db.execute("INSERT INTO favorites (user_id, product_id) VALUES (?, ?)", (user_id, product_id))
        saved = True
    db.commit()
    return saved


def get_product(product_id):
    return get_db().execute(
        """
        SELECT p.id, p.weapon, p.skin, p.quality, p.price, p.image_url, p.stock,
               p.category_id, c.name AS category_name
        FROM products p
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE p.id = ?
        """,
        (product_id,),
    ).fetchone()


def save_product(product_id, weapon, skin, quality, price, image_url, stock, category_id=None):
    db = get_db()
    values = (weapon.strip(), skin.strip(), quality.strip(), price, image_url.strip(), stock, category_id)
    if product_id is None:
        cursor = db.execute(
            "INSERT INTO products (weapon, skin, quality, price, image_url, stock, category_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            values,
        )
    else:
        cursor = db.execute(
            "UPDATE products SET weapon=?, skin=?, quality=?, price=?, image_url=?, stock=?, category_id=? WHERE id=?",
            (*values, product_id),
        )
    db.commit()
    return cursor.lastrowid if product_id is None else cursor.rowcount > 0


def delete_product(product_id):
    import sqlite3

    db = get_db()
    try:
        cursor = db.execute("DELETE FROM products WHERE id = ?", (product_id,))
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.IntegrityError:
        db.rollback()
        return False
