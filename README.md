# LOQ Market (Лабораторна робота №5 — RESTful API з документацією)

Багатосторінковий вебзастосунок та RESTful API для магазину скінів Counter-Strike 2 на **Flask**, **SQLite** та **flasgger**.

## Команда

| Учасник | Роль | GitHub |
|---|---|---|
| Прадійчук Ілля Миколайович | Teamlead | https://github.com/illuwka |
| Завиднюк Влад Володимирович | Developer | https://github.com/flavour676767 |
| Біскій Давид Анатолійович | QA | https://github.com/Crunqz |

Група: **ІПЗ-22**

---

## Короткий опис проєкту та API

Застосунок **LOQ Market** поєднує вебінтерфейс на Jinja2 (каталог скінів, кошик/оформлення замовлень, обране, кабінет користувача, зворотний зв’язок і адмін-панель) із **RESTful JSON API** під префіксом `/api`.

Особливості реалізованого API:
- **Stateless-архітектура**: API не використовує сесії/cookies — кожен запит містить усі необхідні дані.
- **13 endpoints** для роботи з товарами, категоріями, замовленнями та відгуками (працюють із тією самою базою даних SQLite, що й сайт).
- **JSON-формат** запитів, відповідей та повідомлень про помилки (з підтримкою кирилиці без `\uXXXX` та збереженням порядку ключів).
- **Валідація та обробка помилок**: перевірка заголовка `Content-Type: application/json`, синтаксису JSON, типів і значень полів, email-адрес, існування ресурсів, конфліктів цілісності БД, а також глобальне перехоплення `HTTPException`, `sqlite3.Error` та непередбачених винятків для `/api/...`.
- **Інтерактивна документація Swagger (OpenAPI 2.0)** за допомогою `flasgger` на `/apidocs/`.

---

## Використані технології

- **Python 3**
- **Flask 3.1.3** — вебфреймворк і маршрутизація (Blueprints)
- **Werkzeug 3.1.9** — обробка HTTP-винятків (`HTTPException`) та перевірка паролів
- **flasgger 0.9.7.1** — генерація OpenAPI-специфікації (`/apispec_1.json`) та інтерактивного Swagger UI (`/apidocs/`)
- **SQLite (`sqlite3`)** — реляційна база даних (`instance/loq_market.sqlite3`)
- **HTML5 / Jinja2 + Tailwind CSS 4 (CDN)** — інтерфейс вебсторінок

---

## Структура проєкту

```text
lab05/
├── app.py                   # Точка входу Flask, Swagger (flasgger), глобальні JSON-обробники помилок
├── init_db.py               # Скрипт ініціалізації таблиць БД
├── seed_data.py             # Початкові дані (товари, категорії, промокод LOQ10, замовлення)
├── requirements.txt         # Залежності Python (Flask, Werkzeug, flasgger)
├── models/                  # Модулі доступу до даних SQLite
│   ├── __init__.py
│   ├── db.py                # З'єднання з БД, схема таблиць і міграції
│   ├── catalog.py           # Категорії, товари, обране
│   ├── users.py             # Користувачі, ролі, автентифікація
│   ├── orders.py            # Замовлення, позиції, статуси та промокоди
│   └── feedback.py          # Відгуки користувачів
├── routes/                  # Маршрути (Flask Blueprints)
│   ├── __init__.py
│   ├── api.py               # REST API (/api/*) + схеми і YAML-описи OpenAPI для flasgger
│   ├── auth.py              # Вхід, реєстрація, налаштування адміна, кабінет
│   ├── shop.py              # Магазин, обране, оформлення замовлення
│   ├── feedback.py          # Контакти та форма зворотного зв’язку
│   └── admin.py             # Адмін-панель (товари, категорії, користувачі, замовлення, промокоди, відгуки)
├── templates/               # HTML-шаблони Jinja2
├── instance/
│   └── loq_market.sqlite3   # База даних SQLite (створюється автоматично)
├── lab-reports/             # Звіти учасників команди та скріншоти
└── README.md
```

---

## Запуск проєкту

1. Клонуйте репозиторій та перейдіть у директорію проєкту:

```bash
git clone <URL_репозиторію>
cd lab05
```

2. Створіть та активуйте віртуальне середовище Python:

```bash
python3 -m venv .venv
# Linux / macOS:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate
```

3. Встановіть залежності:

```bash
pip install -r requirements.txt
```

4. Запустіть сервер:

```bash
python app.py
```

Після запуску доступні:
- Вебзастосунок: `http://127.0.0.1:5000/`
- Інтерактивна документація Swagger UI (`flasgger`): `http://127.0.0.1:5000/apidocs/`
- OpenAPI-специфікація у форматі JSON: `http://127.0.0.1:5000/apispec_1.json`

---

## Документація REST API

Усі ендпоінти знаходяться в [`routes/api.py`](routes/api.py) під префіксом `/api`.

### Таблиця endpoints

| Метод | Адреса | Призначення | Запит (тіло / параметри) | Коди відповідей |
|---|---|---|---|---|
| `GET` | `/api/products` | Отримати список усіх товарів каталогу | — | `200`, `500` |
| `GET` | `/api/products/<id>` | Отримати товар за ідентифікатором | `id` (path, int) | `200`, `404` |
| `POST` | `/api/products` | Створити новий товар (повертає заголовок `Location`) | JSON: `weapon`, `skin`, `quality`, `price`, опц. `image_url`, `stock`, `category_id` | `201`, `400`, `500` |
| `PUT` | `/api/products/<id>` | Повністю оновити існуючий товар | `id` (path, int) + JSON як у `POST` | `200`, `400`, `404`, `500` |
| `DELETE` | `/api/products/<id>` | Видалити товар (якщо немає пов’язаних замовлень) | `id` (path, int) | `204`, `404`, `409`, `500` |
| `GET` | `/api/categories` | Отримати ієрархічний список категорій | — | `200`, `500` |
| `GET` | `/api/orders` | Отримати список усіх замовлень | — | `200`, `500` |
| `GET` | `/api/orders/<id>` | Отримати замовлення разом із переліком позицій | `id` (path, int) | `200`, `404` |
| `POST` | `/api/orders` | Створити нове замовлення (зменшує залишок, застосовує промокод; повертає `Location`) | JSON: `product_id`, `quantity`, `customer_name`, `customer_email`, опц. `promo_code` | `201`, `400`, `404`, `500` |
| `PATCH` | `/api/orders/<id>` | Оновити статус замовлення (`pending`, `processing`, `shipped`, `completed`, `cancelled`) | `id` (path, int) + JSON: `status` | `200`, `400`, `404`, `500` |
| `DELETE` | `/api/orders/<id>` | Видалити замовлення (повертає залишок на склад, якщо не було скасоване) | `id` (path, int) | `204`, `404`, `500` |
| `GET` | `/api/feedback` | Отримати список усіх відгуків | — | `200`, `500` |
| `POST` | `/api/feedback` | Зберегти новий відгук користувача | JSON: `name`, `email`, `message` | `201`, `400`, `500` |

### Валідація та обробка помилок

Усі помилки для адрес `/api` та `/api/...` повертаються у єдиному JSON-форматі:

```json
{
  "error": "Опис помилки"
}
```

Реалізовано два рівні обробки помилок:
1. **На рівні застосунку ([`app.py`](app.py))**:
   - `handle_http_error` (`@app.errorhandler(HTTPException)`) — перетворює стандартні HTTP-помилки Flask/Werkzeug (`400`, `401`, `403`, `404`, `405`, `409`, `415`, `422`, `500`, `503`) у JSON для `/api/...`, залишаючи HTML-сторінки для звичайного сайту.
   - `handle_unexpected_error` (`@app.errorhandler(Exception)`) — логує непередбачені помилки й повертає `500` у форматі JSON (навіть коли `debug=True`).
2. **На рівні Blueprint ([`routes/api.py`](routes/api.py))**:
   - `handle_database_error` (`@api_bp.errorhandler(sqlite3.Error)`) — перехоплює помилки SQLite і повертає JSON зі статусом `500`.
   - `_get_json_object()` — перевіряє заголовок `Content-Type: application/json`, коректність синтаксису JSON і те, що тіло запиту є JSON-об’єктом (`400`).
   - Валідація полів товарів (`_parse_product_payload`: непорожні рядки, число `price >= 0`, ціле `stock >= 0` без `bool`, перевірка `category_id`), замовлень (додатні `product_id`, `quantity`, коректний email через `_is_valid_email`, валідний `status`, достатній залишок на складі, дійсність промокоду) та відгуків (`name`, `email`, `message`).

### Приклади використання (`curl`)

**Отримати список товарів:**
```bash
curl http://127.0.0.1:5000/api/products
```

**Створити товар (`201 Created`):**
```bash
curl -i -X POST http://127.0.0.1:5000/api/products \
  -H "Content-Type: application/json" \
  -d '{
    "weapon": "AK-47",
    "skin": "Redline",
    "quality": "Field-Tested",
    "price": 25.5,
    "stock": 5,
    "category_id": 5
  }'
```

**Створити замовлення з промокодом (`201 Created`):**
```bash
curl -i -X POST http://127.0.0.1:5000/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": 1,
    "quantity": 1,
    "customer_name": "Іван Петренко",
    "customer_email": "ivan@example.com",
    "promo_code": "LOQ10"
  }'
```

**Оновити статус замовлення (`200 OK`):**
```bash
curl -X PATCH http://127.0.0.1:5000/api/orders/1 \
  -H "Content-Type: application/json" \
  -d '{"status": "processing"}'
```

**Приклад відповіді з помилкою (`404 Not Found`):**
```bash
curl -i http://127.0.0.1:5000/api/products/9999
```
```json
{
  "error": "Товар не знайдено."
}
```

### Swagger / OpenAPI документація (`flasgger`)

У [`app.py`](app.py) підключено `Swagger(app, config=SWAGGER_CONFIG, template=SWAGGER_TEMPLATE)`:
- документуються лише маршрути `/api/...` (через `rule_filter`);
- у `SWAGGER_TEMPLATE["definitions"]` описано 12 OpenAPI-схем (`Product`, `ProductInput`, `Category`, `OrderItem`, `OrderSummary`, `OrderDetail`, `OrderCreateInput`, `OrderStatusInput`, `Feedback`, `FeedbackCreateResponse`, `FeedbackInput`, `ErrorResponse`);
- кожен із 13 ендпоінтів у [`routes/api.py`](routes/api.py) має YAML-опис із параметрами, схемами запитів/відповідей та прикладами (`example` / `examples`), що дозволяє тестувати API прямо на сторінці `/apidocs/` через **Try it out**.

---

## Тестування

У межах перевірки за допомогою `app.test_client()` на тимчасовій базі даних SQLite підтверджено:
- коректну роботу всіх 13 endpoints (`200`, `201` із заголовком `Location`, `204`);
- повернення JSON-помилок `400` (відсутній `Content-Type`, невалідний JSON, не-об’єкт, некоректні поля/email/статус), `404` (неіснуючий ID, неіснуючий маршрут `/api/...`), `405` (недозволений HTTP-метод), `409` (видалення товару із замовленням) та `500` (непередбачені винятки й помилки SQLite);
- доступність `/apidocs/` (`200 OK`), `/apispec_1.json` (`200 OK`, 13 ендпоінтів і 12 схем) та статичних файлів Swagger UI.

> **Примітка щодо звіту (Postman / скріншоти):** файл колекції Postman та скріншоти результатів тестування з Postman і сторінки `/apidocs/` можна додати до `lab-reports/screenshots/` після прогону сценаріїв у Postman.

---

## Сторінки вебзастосунку (функціонал сайту)

- **Головна (`/`)** — вступний блок і добірка популярних скінів
- **Магазин (`/shop`)** — каталог скінів із пошуком, фільтрацією за категоріями/зброєю/якістю/ціною, сортуванням, промокодами та обраним
- **Оформлення замовлення (`/shop/<id>/order`)** — замовлення скіну з перевіркою залишку та застосуванням промокоду
- **Обране (`/favorites`)** — збережені користувачем скіни
- **Мої замовлення (`/account`)** — особиста історія замовлень користувача
- **Автентифікація (`/login`, `/register`, `/setup/admin`)** — вхід, реєстрація клієнта та налаштування першого адміністратора
- **Про нас (`/about`)** — інформація про команду
- **Зворотний зв’язок (`/contacts`)** — контакти та форма надсилання відгуку
- **Адмін-панель (`/admin/*`)** — керування товарами, категоріями, користувачами, замовленнями, промокодами та відгуками

---

## Висновки

У ході лабораторної роботи №5 для наявного вебзастосунку **LOQ Market** розроблено RESTful API на базі Flask Blueprint (`routes/api.py`) із 13 ендпоінтами для роботи з товарами, категоріями, замовленнями та відгуками у форматі JSON. Реалізовано валідацію вхідних даних, коректні HTTP-методи й коди відповідей (`200`, `201`, `204`, `400`, `404`, `405`, `409`, `500`), єдиний формат JSON-помилок і інтерактивну документацію OpenAPI/Swagger за допомогою бібліотеки `flasgger` на `/apidocs/`.
