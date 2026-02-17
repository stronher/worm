#!/usr/bin/env python3
"""Backend completo para Parallax Invest IA (RCS Technology)."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

DB_PATH = os.environ.get("PARALLAX_DB_PATH", "parallax.db")
HOST = os.environ.get("PARALLAX_HOST", "0.0.0.0")
PORT = int(os.environ.get("PARALLAX_PORT", "8090"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()

    def init(self) -> None:
        with self.lock, self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    cash_balance REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    ticker TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, ticker),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    ticker TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    avg_price REAL NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, ticker),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    ticker TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL NOT NULL,
                    notional REAL NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    amount REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    ticker TEXT NOT NULL,
                    horizon_days INTEGER NOT NULL,
                    confidence INTEGER NOT NULL,
                    projected_change REAL NOT NULL,
                    trend TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );
                """
            )

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self.lock, self.conn:
            return self.conn.execute(sql, params)

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        cur = self.execute(sql, params)
        return cur.fetchone()

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        cur = self.execute(sql, params)
        return cur.fetchall()


class InvestmentService:
    def __init__(self, db: Database):
        self.db = db

    def create_user(self, name: str, email: str, initial_cash: float) -> dict[str, Any]:
        now = utc_now()
        cur = self.db.execute(
            "INSERT INTO users(name, email, cash_balance, created_at) VALUES (?, ?, ?, ?)",
            (name, email.lower(), initial_cash, now),
        )
        user_id = int(cur.lastrowid)
        if initial_cash > 0:
            self.db.execute(
                "INSERT INTO transactions(user_id, type, description, amount, created_at) VALUES(?, 'deposit', ?, ?, ?)",
                (user_id, "Depósito inicial", initial_cash, now),
            )
        return self.get_user(user_id)

    def get_user(self, user_id: int) -> dict[str, Any]:
        row = self.db.fetchone(
            "SELECT id, name, email, cash_balance, created_at FROM users WHERE id = ?",
            (user_id,),
        )
        if not row:
            raise ValueError("Usuário não encontrado")
        return dict(row)

    def add_watchlist(self, user_id: int, ticker: str) -> dict[str, Any]:
        self.get_user(user_id)
        now = utc_now()
        self.db.execute(
            "INSERT INTO watchlist(user_id, ticker, created_at) VALUES (?, ?, ?)",
            (user_id, ticker.upper(), now),
        )
        return {"user_id": user_id, "ticker": ticker.upper(), "created_at": now}

    def predict(self, ticker: str, horizon_days: int, user_id: int | None = None) -> dict[str, Any]:
        t = ticker.upper().strip()
        score = 0
        seed = f"{t}-{horizon_days}"
        for ch in seed:
            score = (score * 31 + ord(ch)) % 100000

        confidence = 55 + (score % 40)
        projected_change = round(((score % 1600) / 100) - 6, 2)
        trend = "up" if projected_change >= 0 else "down"
        now = utc_now()

        self.db.execute(
            """
            INSERT INTO predictions(user_id, ticker, horizon_days, confidence, projected_change, trend, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, t, horizon_days, confidence, projected_change, trend, now),
        )

        return {
            "ticker": t,
            "horizon_days": horizon_days,
            "confidence": confidence,
            "projected_change": projected_change,
            "trend": trend,
            "generated_at": now,
            "note": "Simulação demonstrativa para UX do produto.",
        }

    def place_order(self, user_id: int, ticker: str, side: str, quantity: float, price: float) -> dict[str, Any]:
        if side not in {"buy", "sell"}:
            raise ValueError("side deve ser 'buy' ou 'sell'")
        if quantity <= 0 or price <= 0:
            raise ValueError("quantity e price devem ser > 0")

        user = self.get_user(user_id)
        ticker = ticker.upper().strip()
        notional = round(quantity * price, 2)
        now = utc_now()

        pos = self.db.fetchone(
            "SELECT id, quantity, avg_price FROM positions WHERE user_id = ? AND ticker = ?",
            (user_id, ticker),
        )

        if side == "buy":
            if float(user["cash_balance"]) < notional:
                raise ValueError("Saldo insuficiente para compra")
            new_cash = round(float(user["cash_balance"]) - notional, 2)
            self.db.execute("UPDATE users SET cash_balance = ? WHERE id = ?", (new_cash, user_id))

            if pos:
                old_qty = float(pos["quantity"])
                old_avg = float(pos["avg_price"])
                new_qty = old_qty + quantity
                new_avg = round(((old_qty * old_avg) + (quantity * price)) / new_qty, 4)
                self.db.execute(
                    "UPDATE positions SET quantity = ?, avg_price = ?, updated_at = ? WHERE id = ?",
                    (new_qty, new_avg, now, int(pos["id"])),
                )
            else:
                self.db.execute(
                    "INSERT INTO positions(user_id, ticker, quantity, avg_price, updated_at) VALUES(?, ?, ?, ?, ?)",
                    (user_id, ticker, quantity, price, now),
                )

            description = f"Compra {quantity} {ticker} @ {price}"
            tx_amount = -notional

        else:
            if not pos or float(pos["quantity"]) < quantity:
                raise ValueError("Posição insuficiente para venda")

            new_qty = round(float(pos["quantity"]) - quantity, 6)
            new_cash = round(float(user["cash_balance"]) + notional, 2)
            self.db.execute("UPDATE users SET cash_balance = ? WHERE id = ?", (new_cash, user_id))

            if new_qty <= 0:
                self.db.execute("DELETE FROM positions WHERE id = ?", (int(pos["id"]),))
            else:
                self.db.execute(
                    "UPDATE positions SET quantity = ?, updated_at = ? WHERE id = ?",
                    (new_qty, now, int(pos["id"])),
                )

            description = f"Venda {quantity} {ticker} @ {price}"
            tx_amount = notional

        order_cur = self.db.execute(
            """
            INSERT INTO orders(user_id, ticker, side, quantity, price, notional, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'filled', ?)
            """,
            (user_id, ticker, side, quantity, price, notional, now),
        )

        self.db.execute(
            "INSERT INTO transactions(user_id, type, description, amount, created_at) VALUES (?, 'trade', ?, ?, ?)",
            (user_id, description, tx_amount, now),
        )

        return {
            "order_id": int(order_cur.lastrowid),
            "status": "filled",
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "price": price,
            "notional": notional,
            "cash_balance": self.get_user(user_id)["cash_balance"],
        }

    def portfolio(self, user_id: int) -> dict[str, Any]:
        user = self.get_user(user_id)
        positions = [
            dict(row)
            for row in self.db.fetchall(
                "SELECT ticker, quantity, avg_price, updated_at FROM positions WHERE user_id = ? ORDER BY ticker",
                (user_id,),
            )
        ]
        watchlist = [
            row["ticker"]
            for row in self.db.fetchall(
                "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY ticker",
                (user_id,),
            )
        ]
        return {
            "user": user,
            "positions": positions,
            "watchlist": watchlist,
        }

    def transactions(self, user_id: int) -> list[dict[str, Any]]:
        self.get_user(user_id)
        return [
            dict(row)
            for row in self.db.fetchall(
                "SELECT id, type, description, amount, created_at FROM transactions WHERE user_id = ? ORDER BY id DESC",
                (user_id,),
            )
        ]


class ApiHandler(BaseHTTPRequestHandler):
    db: Database
    service: InvestmentService

    def _send(self, status: int, payload: dict[str, Any] | list[Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.path == "/api/users":
                body = self._json()
                name = str(body.get("name", "")).strip()
                email = str(body.get("email", "")).strip().lower()
                initial_cash = float(body.get("initial_cash", 0))
                if not name or not email:
                    self._send(HTTPStatus.BAD_REQUEST, {"error": "name e email são obrigatórios"})
                    return
                user = self.service.create_user(name, email, initial_cash)
                self._send(HTTPStatus.CREATED, user)
                return

            if self.path == "/api/watchlist":
                body = self._json()
                user_id = int(body.get("user_id", 0))
                ticker = str(body.get("ticker", "")).strip()
                if user_id <= 0 or not ticker:
                    self._send(HTTPStatus.BAD_REQUEST, {"error": "user_id e ticker são obrigatórios"})
                    return
                item = self.service.add_watchlist(user_id, ticker)
                self._send(HTTPStatus.CREATED, item)
                return

            if self.path == "/api/predictions":
                body = self._json()
                ticker = str(body.get("ticker", "")).strip()
                horizon = int(body.get("horizon_days", 30))
                user_id = body.get("user_id")
                user_id = int(user_id) if user_id is not None else None
                if not ticker or horizon <= 0:
                    self._send(HTTPStatus.BAD_REQUEST, {"error": "ticker e horizon_days>0 são obrigatórios"})
                    return
                if user_id is not None:
                    self.service.get_user(user_id)
                result = self.service.predict(ticker, horizon, user_id)
                self._send(HTTPStatus.OK, result)
                return

            if self.path == "/api/orders":
                body = self._json()
                user_id = int(body.get("user_id", 0))
                ticker = str(body.get("ticker", "")).strip()
                side = str(body.get("side", "")).strip().lower()
                quantity = float(body.get("quantity", 0))
                price = float(body.get("price", 0))
                result = self.service.place_order(user_id, ticker, side, quantity, price)
                self._send(HTTPStatus.OK, result)
                return

            self._send(HTTPStatus.NOT_FOUND, {"error": "Rota não encontrada"})
        except sqlite3.IntegrityError as exc:
            self._send(HTTPStatus.CONFLICT, {"error": str(exc)})
        except ValueError as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"erro interno: {exc}"})

    def do_GET(self) -> None:  # noqa: N802
        try:
            if self.path == "/health":
                self._send(HTTPStatus.OK, {"status": "ok", "service": "parallax-backend"})
                return

            if self.path.startswith("/api/portfolio/"):
                user_id = int(self.path.split("/")[-1])
                self._send(HTTPStatus.OK, self.service.portfolio(user_id))
                return

            if self.path.startswith("/api/transactions/"):
                user_id = int(self.path.split("/")[-1])
                self._send(HTTPStatus.OK, self.service.transactions(user_id))
                return

            self._send(HTTPStatus.NOT_FOUND, {"error": "Rota não encontrada"})
        except ValueError as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"erro interno: {exc}"})


def run() -> None:
    db = Database(DB_PATH)
    db.init()

    ApiHandler.db = db
    ApiHandler.service = InvestmentService(db)

    server = ThreadingHTTPServer((HOST, PORT), ApiHandler)
    print(f"Parallax backend on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
