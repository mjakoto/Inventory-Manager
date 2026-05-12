import json
import logging
import os
import sqlite3
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from functools import wraps
from hmac import compare_digest

from flask import Flask, Response, current_app, g, jsonify, request, session
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest


REQUEST_COUNT = Counter(
    "inventory_http_requests_total",
    "Total HTTP requests.",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "inventory_http_request_latency_seconds",
    "HTTP request latency in seconds.",
    ["method", "endpoint"],
)
ERROR_COUNT = Counter(
    "inventory_http_errors_total",
    "Total HTTP responses with status >= 400.",
    ["method", "endpoint", "status"],
)
LOW_STOCK_GAUGE = Gauge(
    "inventory_low_stock_items",
    "Number of inventory items currently below or at their low-stock threshold.",
)
ITEM_COUNT_GAUGE = Gauge(
    "inventory_total_items",
    "Total number of inventory items.",
)

WRITE_BUCKETS = defaultdict(deque)
DEFAULT_LOCATIONS = ["Warehouse A", "Warehouse B", "Retail Floor", "Receiving"]
DEFAULT_CATEGORIES = ["Hardware", "Peripherals", "Networking", "Cables", "Office"]


class APIError(Exception):
    def __init__(self, message, status_code=400, details=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        for key in (
            "method",
            "path",
            "endpoint",
            "status_code",
            "duration_ms",
            "remote_addr",
            "authenticated",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload)


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "change-me-for-production"),
        DATABASE=os.getenv("DATABASE_PATH", os.path.join(app.root_path, "inventory.db")),
        ADMIN_USERNAME=os.getenv("ADMIN_USERNAME", "admin"),
        ADMIN_PASSWORD=os.getenv("ADMIN_PASSWORD", "inventory-admin"),
        WRITE_RATE_LIMIT=int(os.getenv("WRITE_RATE_LIMIT", "30")),
        WRITE_RATE_WINDOW_SECONDS=int(os.getenv("WRITE_RATE_WINDOW_SECONDS", "60")),
    )

    if test_config:
        app.config.update(test_config)

    configure_logging(app)

    with app.app_context():
        init_db()
        update_inventory_metrics()

    @app.before_request
    def before_request():
        g.request_started = time.perf_counter()

    @app.after_request
    def after_request(response):
        duration = time.perf_counter() - g.get("request_started", time.perf_counter())
        endpoint = request.endpoint or "unknown"

        REQUEST_COUNT.labels(request.method, endpoint, str(response.status_code)).inc()
        REQUEST_LATENCY.labels(request.method, endpoint).observe(duration)
        if response.status_code >= 400:
            ERROR_COUNT.labels(request.method, endpoint, str(response.status_code)).inc()

        current_app.logger.info(
            "request complete",
            extra={
                "method": request.method,
                "path": request.path,
                "endpoint": endpoint,
                "status_code": response.status_code,
                "duration_ms": round(duration * 1000, 2),
                "remote_addr": request.headers.get("X-Forwarded-For", request.remote_addr),
                "authenticated": bool(session.get("authenticated")),
            },
        )
        return response

    @app.errorhandler(APIError)
    def handle_api_error(error):
        return jsonify(
            {
                "status": "error",
                "message": error.message,
                "details": error.details,
            }
        ), error.status_code

    @app.errorhandler(404)
    def handle_not_found(_error):
        return jsonify({"status": "error", "message": "Resource not found"}), 404

    @app.errorhandler(500)
    def handle_server_error(error):
        current_app.logger.exception("unhandled server error", exc_info=error)
        return jsonify({"status": "error", "message": "Internal server error"}), 500

    @app.route("/healthz", methods=["GET"])
    def healthz():
        return jsonify({"status": "ok", "timestamp": utc_now()})

    @app.route("/readyz", methods=["GET"])
    def readyz():
        conn = get_db_connection()
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
        return jsonify({"status": "ready", "database": "ok"})

    @app.route("/metrics", methods=["GET"])
    def metrics():
        update_inventory_metrics()
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

    @app.route("/session", methods=["GET"])
    def get_session():
        return jsonify(
            {
                "authenticated": bool(session.get("authenticated")),
                "username": session.get("username"),
            }
        )

    @app.route("/login", methods=["POST"])
    @rate_limit()
    def login():
        payload = get_json_payload()
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", "")).strip()

        if not compare_digest(username, app.config["ADMIN_USERNAME"]) or not compare_digest(
            password, app.config["ADMIN_PASSWORD"]
        ):
            raise APIError("Invalid username or password", status_code=401)

        session["authenticated"] = True
        session["username"] = username
        return jsonify({"status": "success", "authenticated": True, "username": username})

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        return jsonify({"status": "success", "authenticated": False})

    @app.route("/dashboard", methods=["GET"])
    def dashboard():
        items = fetch_items()
        low_stock_items = [item for item in items if item["is_low_stock"]]
        summary = build_summary(items)
        return jsonify(
            {
                "summary": summary,
                "low_stock_items": low_stock_items,
                "locations": sorted({item["location"] for item in items}),
                "categories": sorted({item["category"] for item in items}),
            }
        )

    @app.route("/items", methods=["GET"])
    def list_items():
        query = build_item_query(request.args)
        conn = get_db_connection()
        try:
            rows = conn.execute(query["sql"], query["params"]).fetchall()
        finally:
            conn.close()

        items = [serialize_item(row) for row in rows]
        return jsonify(
            {
                "items": items,
                "summary": build_summary(items),
                "filters": {
                    "search": request.args.get("search", "").strip(),
                    "category": request.args.get("category", "").strip(),
                    "location": request.args.get("location", "").strip(),
                    "stock_status": request.args.get("stock_status", "all").strip(),
                    "sort": request.args.get("sort", "updated_at").strip(),
                    "direction": request.args.get("direction", "desc").strip(),
                },
            }
        )

    @app.route("/items", methods=["POST"])
    @require_auth
    @rate_limit()
    def create_item():
        payload = validate_item_payload(get_json_payload(), partial=False)
        conn = get_db_connection()
        timestamp = utc_now()

        try:
            cursor = conn.execute(
                """
                INSERT INTO items (name, sku, quantity, location, category, low_stock_threshold, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["name"],
                    payload["sku"],
                    payload["quantity"],
                    payload["location"],
                    payload["category"],
                    payload["low_stock_threshold"],
                    timestamp,
                ),
            )
            conn.execute(
                """
                INSERT INTO history (action, item, details, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (
                    "CREATED",
                    payload["name"],
                    json.dumps(payload),
                    timestamp,
                ),
            )
            conn.commit()

            row = conn.execute("SELECT * FROM items WHERE id = ?", (cursor.lastrowid,)).fetchone()
        except sqlite3.IntegrityError as error:
            conn.rollback()
            raise APIError("SKU must be unique", status_code=409) from error
        finally:
            conn.close()

        update_inventory_metrics()
        return jsonify({"status": "success", "item": serialize_item(row)}), 201

    @app.route("/items/<int:item_id>", methods=["PUT"])
    @require_auth
    @rate_limit()
    def update_item(item_id):
        conn = get_db_connection()
        existing = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if not existing:
            conn.close()
            raise APIError("Item not found", status_code=404)

        merged_payload = dict(serialize_item(existing))
        merged_payload.update(get_json_payload())
        payload = validate_item_payload(merged_payload, partial=False)
        timestamp = utc_now()

        changes = {
            field: {"from": serialize_item(existing)[field], "to": payload[field]}
            for field in ("name", "sku", "quantity", "location", "category", "low_stock_threshold")
            if serialize_item(existing)[field] != payload[field]
        }

        if not changes:
            conn.close()
            return jsonify({"status": "success", "item": serialize_item(existing), "changes": {}})

        try:
            conn.execute(
                """
                UPDATE items
                SET name = ?, sku = ?, quantity = ?, location = ?, category = ?, low_stock_threshold = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload["name"],
                    payload["sku"],
                    payload["quantity"],
                    payload["location"],
                    payload["category"],
                    payload["low_stock_threshold"],
                    timestamp,
                    item_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO history (action, item, details, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (
                    "UPDATED",
                    payload["name"],
                    json.dumps(changes),
                    timestamp,
                ),
            )
            conn.commit()

            row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        except sqlite3.IntegrityError as error:
            conn.rollback()
            raise APIError("SKU must be unique", status_code=409) from error
        finally:
            conn.close()

        update_inventory_metrics()
        return jsonify({"status": "success", "item": serialize_item(row), "changes": changes})

    @app.route("/items/<int:item_id>", methods=["DELETE"])
    @require_auth
    @rate_limit()
    def delete_item(item_id):
        conn = get_db_connection()
        row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if not row:
            conn.close()
            raise APIError("Item not found", status_code=404)

        item = serialize_item(row)
        conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
        conn.execute(
            """
            INSERT INTO history (action, item, details, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            ("DELETED", item["name"], json.dumps(item), utc_now()),
        )
        conn.commit()
        conn.close()

        update_inventory_metrics()
        return jsonify({"status": "success"})

    @app.route("/history", methods=["GET"])
    def history():
        limit = parse_positive_int(request.args.get("limit", "25"), "limit")
        conn = get_db_connection()
        try:
            rows = conn.execute(
                "SELECT action, item, details, timestamp FROM history ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            conn.close()

        history_entries = []
        for row in rows:
            details = row["details"]
            parsed_details = None
            if details:
                try:
                    parsed_details = json.loads(details)
                except json.JSONDecodeError:
                    parsed_details = {"message": details}

            history_entries.append(
                {
                    "action": row["action"],
                    "item": row["item"],
                    "details": parsed_details,
                    "timestamp": row["timestamp"],
                }
            )

        return jsonify({"history": history_entries})

    @app.route("/history/clear", methods=["POST"])
    @require_auth
    @rate_limit()
    def clear_history():
        conn = get_db_connection()
        conn.execute("DELETE FROM history")
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})

    @app.route("/data", methods=["GET"])
    def legacy_data():
        return list_items()

    @app.route("/add", methods=["POST"])
    @require_auth
    @rate_limit()
    def legacy_add():
        payload = get_json_payload()
        translated = {
            "name": payload.get("item", ""),
            "sku": build_default_sku(payload.get("item", "Inventory Item")),
            "quantity": 0,
            "location": DEFAULT_LOCATIONS[0],
            "category": DEFAULT_CATEGORIES[0],
            "low_stock_threshold": 0,
        }
        request.environ["inventory.payload_override"] = translated
        return create_item()

    @app.route("/update", methods=["POST"])
    @require_auth
    @rate_limit()
    def legacy_update():
        payload = get_json_payload()
        item_id = payload.get("id")
        if not item_id:
            raise APIError("Legacy update requires an item id", status_code=400)
        conn = get_db_connection()
        row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        conn.close()
        if not row:
            raise APIError("Item not found", status_code=404)
        item = serialize_item(row)
        translated = {
            **item,
            "name": payload.get("new_name", item["name"]),
        }
        request.environ["inventory.payload_override"] = translated
        return update_item(int(item_id))

    @app.route("/delete", methods=["POST"])
    @require_auth
    @rate_limit()
    def legacy_delete():
        payload = get_json_payload()
        item_id = payload.get("id")
        if not item_id:
            raise APIError("Legacy delete requires an item id", status_code=400)
        return delete_item(int(item_id))

    @app.route("/clear_history", methods=["POST"])
    @require_auth
    @rate_limit()
    def legacy_clear_history():
        return clear_history()

    return app


def configure_logging(app):
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    app.logger.handlers.clear()
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)


def get_db_connection():
    conn = sqlite3.connect(current_app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                sku TEXT,
                quantity INTEGER NOT NULL DEFAULT 0,
                location TEXT NOT NULL DEFAULT 'Warehouse A',
                category TEXT NOT NULL DEFAULT 'Hardware',
                low_stock_threshold INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                item TEXT NOT NULL,
                details TEXT,
                timestamp TEXT NOT NULL
            )
            """
        )

        ensure_column(conn, "items", "sku", "TEXT")
        ensure_column(conn, "items", "quantity", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "items", "location", "TEXT NOT NULL DEFAULT 'Warehouse A'")
        ensure_column(conn, "items", "category", "TEXT NOT NULL DEFAULT 'Hardware'")
        ensure_column(conn, "items", "low_stock_threshold", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "items", "updated_at", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "history", "details", "TEXT")

        rows = conn.execute("SELECT id, name, sku, updated_at FROM items").fetchall()
        for row in rows:
            sku = row["sku"] or build_default_sku(row["name"], row["id"])
            updated_at = row["updated_at"] or utc_now()
            conn.execute(
                "UPDATE items SET sku = ?, updated_at = ? WHERE id = ?",
                (sku, updated_at, row["id"]),
            )

        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_items_sku ON items(sku)")
        conn.commit()
    finally:
        conn.close()


def ensure_column(conn, table_name, column_name, column_definition):
    columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    if column_name not in {column["name"] for column in columns}:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def build_default_sku(name, row_id=None):
    base = "".join(char for char in str(name).upper() if char.isalnum())[:6] or "ITEM"
    suffix = str(row_id or int(time.time()))[-4:]
    return f"{base}-{suffix}"


def get_json_payload():
    payload_override = request.environ.get("inventory.payload_override")
    if payload_override is not None:
        return payload_override
    payload = request.get_json(silent=True)
    if payload is None:
        raise APIError("Request body must be valid JSON", status_code=400)
    return payload


def parse_positive_int(raw_value, field_name):
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as error:
        raise APIError(f"{field_name} must be an integer", status_code=400) from error
    if value <= 0:
        raise APIError(f"{field_name} must be greater than zero", status_code=400)
    return value


def normalize_text(value, field_name, required=True, default_value=None):
    normalized = str(value or "").strip()
    if not normalized and default_value is not None:
        normalized = default_value
    if required and not normalized:
        raise APIError(f"{field_name} is required", status_code=400)
    return normalized


def normalize_non_negative_int(value, field_name):
    try:
        normalized = int(value)
    except (TypeError, ValueError) as error:
        raise APIError(f"{field_name} must be an integer", status_code=400) from error
    if normalized < 0:
        raise APIError(f"{field_name} must be zero or greater", status_code=400)
    return normalized


def validate_item_payload(payload, partial=False):
    if not isinstance(payload, dict):
        raise APIError("Request body must be a JSON object", status_code=400)

    if partial:
        raise APIError("Partial updates are not supported in this version", status_code=400)

    name = normalize_text(payload.get("name"), "name")
    sku = normalize_text(payload.get("sku"), "sku").upper()
    quantity = normalize_non_negative_int(payload.get("quantity"), "quantity")
    location = normalize_text(payload.get("location"), "location", default_value=DEFAULT_LOCATIONS[0])
    category = normalize_text(payload.get("category"), "category", default_value=DEFAULT_CATEGORIES[0])
    low_stock_threshold = normalize_non_negative_int(
        payload.get("low_stock_threshold"),
        "low_stock_threshold",
    )

    return {
        "name": name,
        "sku": sku,
        "quantity": quantity,
        "location": location,
        "category": category,
        "low_stock_threshold": low_stock_threshold,
    }


def require_auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("authenticated"):
            raise APIError("Authentication required", status_code=401)
        return func(*args, **kwargs)

    return wrapper


def rate_limit():
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            remote_addr = request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"
            key = (remote_addr, request.endpoint)
            bucket = WRITE_BUCKETS[key]
            now = time.time()
            window = current_app.config["WRITE_RATE_WINDOW_SECONDS"]
            limit = current_app.config["WRITE_RATE_LIMIT"]

            while bucket and bucket[0] <= now - window:
                bucket.popleft()

            if len(bucket) >= limit:
                raise APIError("Rate limit exceeded. Please retry shortly.", status_code=429)

            bucket.append(now)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def serialize_item(row):
    quantity = int(row["quantity"])
    threshold = int(row["low_stock_threshold"])
    return {
        "id": row["id"],
        "name": row["name"],
        "sku": row["sku"],
        "quantity": quantity,
        "location": row["location"],
        "category": row["category"],
        "low_stock_threshold": threshold,
        "updated_at": row["updated_at"],
        "is_low_stock": quantity <= threshold,
    }


def fetch_items():
    conn = get_db_connection()
    try:
        rows = conn.execute("SELECT * FROM items ORDER BY updated_at DESC").fetchall()
    finally:
        conn.close()
    return [serialize_item(row) for row in rows]


def build_summary(items):
    low_stock_items = [item for item in items if item["is_low_stock"]]
    return {
        "total_items": len(items),
        "total_units": sum(item["quantity"] for item in items),
        "low_stock_count": len(low_stock_items),
        "categories": len({item["category"] for item in items}),
        "locations": len({item["location"] for item in items}),
    }


def build_item_query(args):
    allowed_sorts = {
        "name": "name",
        "sku": "sku",
        "quantity": "quantity",
        "location": "location",
        "category": "category",
        "updated_at": "updated_at",
        "low_stock_threshold": "low_stock_threshold",
    }

    sort = allowed_sorts.get(args.get("sort", "updated_at"), "updated_at")
    direction = "ASC" if args.get("direction", "desc").lower() == "asc" else "DESC"

    where_clauses = []
    params = []

    search = args.get("search", "").strip().lower()
    if search:
        where_clauses.append(
            "(LOWER(name) LIKE ? OR LOWER(sku) LIKE ? OR LOWER(location) LIKE ? OR LOWER(category) LIKE ?)"
        )
        term = f"%{search}%"
        params.extend([term, term, term, term])

    category = args.get("category", "").strip()
    if category:
        where_clauses.append("category = ?")
        params.append(category)

    location = args.get("location", "").strip()
    if location:
        where_clauses.append("location = ?")
        params.append(location)

    stock_status = args.get("stock_status", "all").strip()
    if stock_status == "low_stock":
        where_clauses.append("quantity <= low_stock_threshold")
    elif stock_status == "healthy":
        where_clauses.append("quantity > low_stock_threshold")

    sql = "SELECT * FROM items"
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    sql += f" ORDER BY {sort} {direction}, id DESC"

    return {"sql": sql, "params": params}


def update_inventory_metrics():
    conn = get_db_connection()
    try:
        totals = conn.execute("SELECT COUNT(*) AS item_count FROM items").fetchone()
        low_stock = conn.execute(
            "SELECT COUNT(*) AS low_stock_count FROM items WHERE quantity <= low_stock_threshold"
        ).fetchone()
    finally:
        conn.close()

    ITEM_COUNT_GAUGE.set(totals["item_count"])
    LOW_STOCK_GAUGE.set(low_stock["low_stock_count"])


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
