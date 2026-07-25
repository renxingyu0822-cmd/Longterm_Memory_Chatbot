import os
import sys
import tempfile
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from market_data import DemoMarketDataProvider  # noqa: E402
from market_db import MarketDatabase  # noqa: E402
from market_service import MarketService, service as route_service  # noqa: E402
from prediction import HORIZONS, backtest, predict_trends, risk_metrics, simulate_probability_strategy  # noqa: E402


ASSET = {
    "symbol": "TEST",
    "provider_symbol": "TEST",
    "name": "Test Asset",
    "asset_class": "stock",
    "subclass": "us",
    "market": "US",
    "exchange": "NASDAQ",
    "currency": "USD",
    "timezone": "America/New_York",
    "source": "test",
}


class MarketDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = MarketDatabase(Path(self.temp_dir.name) / "investment.db")
        self.asset = self.db.ensure_asset(ASSET)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_watchlist_is_independent_from_positions(self):
        self.db.add_watchlist(self.asset["id"])
        self.assertEqual(len(self.db.list_watchlist()), 1)
        self.assertEqual(self.db.calculate_positions(), [])

        self.db.add_transaction(
            {
                "asset_id": self.asset["id"],
                "transaction_type": "buy",
                "occurred_at": "2026-01-01T10:00:00+00:00",
                "quantity": 10,
                "price": 100,
                "fees": 10,
                "currency": "USD",
            }
        )
        self.db.remove_watchlist(self.asset["id"])
        self.assertEqual(self.db.list_watchlist(), [])
        self.assertEqual(len(self.db.calculate_positions()), 1)

    def test_weighted_cost_and_profit_are_recalculated_from_transactions(self):
        asset_id = self.asset["id"]
        self.db.add_transaction(
            {
                "asset_id": asset_id,
                "transaction_type": "buy",
                "occurred_at": "2026-01-01T10:00:00+00:00",
                "quantity": 10,
                "price": 100,
                "fees": 10,
            }
        )
        self.db.add_transaction(
            {
                "asset_id": asset_id,
                "transaction_type": "sell",
                "occurred_at": "2026-02-01T10:00:00+00:00",
                "quantity": 4,
                "price": 130,
                "fees": 2,
            }
        )
        self.db.upsert_quote(
            asset_id,
            {
                "price": 120,
                "previous_close": 118,
                "currency": "USD",
                "quote_time": "2026-02-01T15:00:00+00:00",
                "source": "test",
            },
        )

        position = self.db.calculate_positions()[0]
        self.assertAlmostEqual(position["quantity"], 6)
        self.assertAlmostEqual(position["average_cost"], 101)
        self.assertAlmostEqual(position["realized_profit"], 114)
        self.assertAlmostEqual(position["unrealized_profit"], 114)
        self.assertAlmostEqual(position["total_profit"], 228)

    def test_rejects_overselling(self):
        with self.assertRaisesRegex(ValueError, "more than"):
            self.db.add_transaction(
                {
                    "asset_id": self.asset["id"],
                    "transaction_type": "sell",
                    "quantity": 1,
                    "price": 100,
                }
            )


class PredictionTests(unittest.TestCase):
    def setUp(self):
        self.provider = DemoMarketDataProvider()
        self.asset = self.provider.search("AAPL", "stock", "us")[0]
        self.prices = [bar["close"] for bar in self.provider.history(self.asset, 360)]

    def test_four_horizons_have_normalized_probabilities(self):
        predictions = predict_trends(self.prices)
        self.assertEqual([item["horizon_days"] for item in predictions], list(HORIZONS))
        for item in predictions:
            total = item["probability_up"] + item["probability_flat"] + item["probability_down"]
            self.assertAlmostEqual(total, 1.0)
            self.assertLess(item["expected_low"], item["expected_high"])

    def test_backtest_risk_and_simulation_are_available(self):
        performance = backtest(self.prices)
        self.assertEqual(set(performance), {"1", "3", "5", "20"})
        self.assertGreater(performance["5"]["sample_count"], 100)
        self.assertIn(risk_metrics(self.prices)["risk_level"], {"low", "medium", "high"})
        simulation = simulate_probability_strategy(self.prices)
        self.assertIn("strategy_return", simulation)
        self.assertEqual(simulation["disclaimer"], "历史模拟，不代表未来收益")


class MarketServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database = MarketDatabase(Path(self.temp_dir.name) / "investment.db")
        self.service = MarketService(database, DemoMarketDataProvider())

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_search_add_refresh_and_dashboard(self):
        result = self.service.search("沪深300", "fund", "exchange_traded")[0]
        item = self.service.add_watchlist({"asset": result})
        self.assertEqual(len(item["predictions"]), 4)
        dashboard = self.service.dashboard(refresh_missing=False)
        self.assertEqual(len(dashboard["watchlist_only"]), 1)
        self.assertEqual(dashboard["positions"], [])

        self.service.add_transaction(
            {
                "asset_id": item["id"],
                "transaction_type": "buy",
                "occurred_at": "2026-07-25T10:00:00+08:00",
                "quantity": 100,
                "price": 4,
                "fees": 1,
            }
        )
        dashboard = self.service.dashboard(refresh_missing=False)
        self.assertEqual(len(dashboard["positions"]), 1)
        self.assertEqual(len(dashboard["watchlist_only"]), 0)


class MarketRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_module

        cls.app_module = app_module

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db = route_service.db
        self.original_provider = route_service.provider
        route_service.db = MarketDatabase(Path(self.temp_dir.name) / "routes.db")
        route_service.provider = DemoMarketDataProvider()
        route_service._analysis_cache.clear()
        self.app_module.app.config.update(TESTING=True)
        self.client = self.app_module.app.test_client()

    def tearDown(self):
        route_service.db = self.original_db
        route_service.provider = self.original_provider
        route_service._analysis_cache.clear()
        self.temp_dir.cleanup()

    def test_market_page_and_chat_entry_exist(self):
        market_response = self.client.get("/market")
        self.assertEqual(market_response.status_code, 200)
        self.assertIn("资产观察室", market_response.get_data(as_text=True))
        chat_response = self.client.get("/")
        self.assertIn('id="market-link"', chat_response.get_data(as_text=True))

    def test_search_watchlist_transaction_and_dashboard_flow(self):
        search = self.client.get(
            "/api/market/search?q=AAPL&asset_class=stock&subclass=us"
        )
        asset = search.get_json()["results"][0]

        watch = self.client.post("/api/market/watchlist", json={"asset": asset})
        self.assertEqual(watch.status_code, 201)
        asset_id = watch.get_json()["item"]["id"]

        transaction = self.client.post(
            "/api/portfolio/transactions",
            json={
                "asset_id": asset_id,
                "transaction_type": "buy",
                "occurred_at": "2026-07-25T10:00:00-04:00",
                "quantity": 2,
                "price": 200,
                "fees": 1,
                "currency": "USD",
            },
        )
        self.assertEqual(transaction.status_code, 201)
        dashboard = self.client.get("/api/market/dashboard").get_json()
        self.assertEqual(len(dashboard["positions"]), 1)
        self.assertEqual(len(dashboard["watchlist_only"]), 0)
        self.assertEqual(len(dashboard["positions"][0]["predictions"]), 4)


if __name__ == "__main__":
    unittest.main()
