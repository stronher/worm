import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import backend


class BackendApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.NamedTemporaryFile(delete=False)
        cls.tmp.close()

        cls.db = backend.Database(cls.tmp.name)
        cls.db.init()
        cls.service = backend.InvestmentService(cls.db)

        backend.ApiHandler.db = cls.db
        backend.ApiHandler.service = cls.service

        cls.server = ThreadingHTTPServer(("127.0.0.1", 18090), backend.ApiHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.2)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        os.unlink(cls.tmp.name)

    def request(self, method, path, payload=None):
        headers = {}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            f"http://127.0.0.1:18090{path}", method=method, data=data, headers=headers
        )

        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                body = response.read().decode("utf-8")
                return response.status, json.loads(body)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            return exc.code, json.loads(body)

    def test_full_investing_flow(self):
        status, user = self.request(
            "POST",
            "/api/users",
            {"name": "Alice", "email": "alice@example.com", "initial_cash": 10000},
        )
        self.assertEqual(status, 201)

        uid = user["id"]

        status, wl = self.request("POST", "/api/watchlist", {"user_id": uid, "ticker": "PETR4"})
        self.assertEqual(status, 201)
        self.assertEqual(wl["ticker"], "PETR4")

        status, pred = self.request(
            "POST", "/api/predictions", {"user_id": uid, "ticker": "PETR4", "horizon_days": 30}
        )
        self.assertEqual(status, 200)
        self.assertIn(pred["trend"], ["up", "down"])

        status, buy = self.request(
            "POST",
            "/api/orders",
            {"user_id": uid, "ticker": "PETR4", "side": "buy", "quantity": 10, "price": 30},
        )
        self.assertEqual(status, 200)
        self.assertEqual(buy["status"], "filled")

        status, sell = self.request(
            "POST",
            "/api/orders",
            {"user_id": uid, "ticker": "PETR4", "side": "sell", "quantity": 5, "price": 33},
        )
        self.assertEqual(status, 200)

        status, portfolio = self.request("GET", f"/api/portfolio/{uid}")
        self.assertEqual(status, 200)
        self.assertEqual(len(portfolio["positions"]), 1)
        self.assertEqual(portfolio["positions"][0]["ticker"], "PETR4")

        status, txs = self.request("GET", f"/api/transactions/{uid}")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(txs), 3)

    def test_buy_with_insufficient_balance(self):
        status, user = self.request(
            "POST",
            "/api/users",
            {"name": "Bob", "email": "bob@example.com", "initial_cash": 10},
        )
        self.assertEqual(status, 201)

        status, response = self.request(
            "POST",
            "/api/orders",
            {"user_id": user["id"], "ticker": "VALE3", "side": "buy", "quantity": 1, "price": 100},
        )
        self.assertEqual(status, 400)
        self.assertIn("Saldo insuficiente", response["error"])


if __name__ == "__main__":
    unittest.main()
