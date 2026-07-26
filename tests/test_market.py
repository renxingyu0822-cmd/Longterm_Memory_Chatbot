import io
import os
import sys
import tempfile
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from market_data import DemoMarketDataProvider, EastmoneyFundProvider, MarketDataError  # noqa: E402
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


class StubEastmoneyFundProvider(EastmoneyFundProvider):
    def _get_json(self, url, params):
        if url == self.search_url:
            return {
                "ErrCode": 0,
                "Datas": [
                    {
                        "CODE": "026789",
                        "NAME": "中欧上证科创板人工智能指数A",
                        "CATEGORYDESC": "基金",
                        "FundBaseInfo": {
                            "SHORTNAME": "中欧上证科创板人工智能指数A",
                            "DWJZ": 0.8302,
                            "FSRQ": "2026-07-24",
                        },
                    }
                ],
            }
        return {}

    def _get_text(self, url):
        return (
            'var Data_netWorthTrend = ['
            '{"x":1784822400000,"y":0.8302},'
            '{"x":1784736000000,"y":0.8401}'
            '];'
        )


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

    def test_buy_automatically_adds_asset_to_watchlist(self):
        self.db.add_transaction(
            {
                "asset_id": self.asset["id"],
                "transaction_type": "buy",
                "occurred_at": "2026-01-01T10:00:00+00:00",
                "quantity": 2,
                "price": 100,
            }
        )

        self.assertEqual([item["id"] for item in self.db.list_watchlist()], [self.asset["id"]])

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

    def test_predictions_follow_the_current_quote_instead_of_a_later_bad_refresh(self):
        def predictions(probability_up):
            return [
                {
                    "horizon_days": horizon,
                    "probability_up": probability_up,
                    "probability_flat": 0.3,
                    "probability_down": 0.7 - probability_up,
                    "expected_low": -2,
                    "expected_high": 2,
                    "confidence": "low",
                }
                for horizon in HORIZONS
            ]

        asset_id = self.asset["id"]
        official_quote = {
            "price": 0.8302,
            "currency": "CNY",
            "quote_time": "2026-07-24T20:00:00+08:00",
            "source": "eastmoney",
            "is_delayed": True,
        }
        self.db.upsert_quote(asset_id, official_quote)
        self.db.save_predictions(asset_id, official_quote["quote_time"], 0.8302, predictions(0.4), "test")
        self.db.save_predictions(asset_id, "2026-07-25T20:00:00+08:00", 96.5998, predictions(0.6), "test")

        self.db.upsert_quote(asset_id, official_quote)
        latest = self.db.latest_predictions(asset_id)
        self.assertEqual(len(latest), 4)
        self.assertTrue(all(item["base_price"] == 0.8302 for item in latest))

    def test_predictions_for_the_same_quote_are_corrected(self):
        asset_id = self.asset["id"]
        quote_time = "2026-07-24T20:00:00+08:00"
        self.db.upsert_quote(
            asset_id,
            {"price": 0.8302, "currency": "CNY", "quote_time": quote_time, "source": "test"},
        )
        original = [{
            "horizon_days": 1,
            "probability_up": 0.8,
            "probability_flat": 0.1,
            "probability_down": 0.1,
            "expected_low": -99,
            "expected_high": 999,
            "confidence": "high",
        }]
        corrected = [{
            "horizon_days": 1,
            "probability_up": 0.3,
            "probability_flat": 0.4,
            "probability_down": 0.3,
            "expected_low": -2,
            "expected_high": 2,
            "confidence": "low",
        }]
        self.db.save_predictions(asset_id, quote_time, 96.5998, original, "test")
        self.db.save_predictions(asset_id, quote_time, 0.8302, corrected, "test")

        latest = self.db.latest_predictions(asset_id)
        self.assertEqual(len(latest), 1)
        self.assertEqual(latest[0]["base_price"], 0.8302)
        self.assertEqual(latest[0]["expected_high"], 2)


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


class DemoMarketDataProviderTests(unittest.TestCase):
    def test_unknown_otc_fund_never_gets_a_stock_like_demo_price(self):
        provider = DemoMarketDataProvider()
        asset = {
            "symbol": "026789",
            "provider_symbol": "026789.OF",
            "name": "中欧上证科创板人工智能指数A",
            "asset_class": "fund",
            "subclass": "otc",
            "currency": "CNY",
        }

        with self.assertRaisesRegex(MarketDataError, "keeping the last official NAV"):
            provider.quote(asset)
        with self.assertRaisesRegex(MarketDataError, "keeping official history"):
            provider.history(asset)


class EastmoneyFundProviderTests(unittest.TestCase):
    def setUp(self):
        self.provider = StubEastmoneyFundProvider()

    def test_search_quote_and_history_for_otc_fund(self):
        asset = self.provider.search("026789", "fund", "otc")[0]
        self.assertEqual(asset["provider_symbol"], "026789.OF")
        self.assertEqual(asset["source"], "eastmoney")

        quote = self.provider.quote(asset)
        self.assertEqual(quote["price"], 0.8302)
        self.assertEqual(quote["quote_time"], "2026-07-24T20:00:00+08:00")
        self.assertTrue(quote["is_delayed"])

        history = self.provider.history(asset)
        self.assertEqual([item["date"] for item in history], ["2026-07-23", "2026-07-24"])
        self.assertEqual(history[-1]["close"], 0.8302)


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

    def test_import_matches_fund_name_with_omitted_launch_marker(self):
        candidates = [
            {
                "symbol": "022364",
                "provider_symbol": "022364.OF",
                "name": "永赢科技智选混合发起A",
                "asset_class": "fund",
                "subclass": "otc",
            },
            {
                "symbol": "022365",
                "provider_symbol": "022365.OF",
                "name": "永赢科技智选混合发起C",
                "asset_class": "fund",
                "subclass": "otc",
            },
        ]
        self.service.search = lambda query, asset_class, subclass: candidates

        matched = self.service._resolve_import_asset({
            "name": "永赢科技智选混合A",
            "asset_class": "fund",
            "subclass": "otc",
        })

        self.assertEqual(matched["symbol"], "022364")

    def test_failed_otc_refresh_restores_the_latest_official_nav(self):
        class UnavailableProvider:
            def quote(self, asset):
                raise MarketDataError("offline")

            def history(self, asset, days=520):
                raise MarketDataError("offline")

        fund = self.service.db.ensure_asset(
            {
                "symbol": "026789",
                "provider_symbol": "026789.OF",
                "name": "中欧上证科创板人工智能指数A",
                "asset_class": "fund",
                "subclass": "otc",
                "market": "CN",
                "exchange": "OTC",
                "currency": "CNY",
                "source": "eastmoney",
            }
        )
        self.service.db.upsert_daily_bars(
            fund["id"],
            [
                {"date": "2026-07-23", "close": 0.8362, "source": "eastmoney"},
                {"date": "2026-07-24", "close": 0.8302, "source": "eastmoney"},
            ],
        )
        self.service.db.upsert_quote(
            fund["id"],
            {
                "price": 96.5998,
                "previous_close": 99.2399,
                "currency": "CNY",
                "quote_time": "2026-07-25T20:00:00+08:00",
                "source": "demo",
                "is_delayed": True,
            },
        )
        self.service.provider = UnavailableProvider()

        refreshed = self.service.refresh_asset(fund["id"], force=True)
        self.assertEqual(refreshed["quote"]["price"], 0.8302)
        self.assertEqual(refreshed["quote"]["source"], "eastmoney")
        self.assertEqual(refreshed["quote"]["quote_time"], "2026-07-24T20:00:00+08:00")


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
        self.assertIn("图片 / 文件一键导入", market_response.get_data(as_text=True))
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

    def test_csv_can_import_holdings_and_automatically_watch_them(self):
        response = self.client.post(
            "/api/portfolio/import",
            data={
                "target": "holdings",
                "file": (
                    io.BytesIO("股票代码,持仓数量,平均成本\nAAPL,3,198.5\n".encode("utf-8")),
                    "positions.csv",
                ),
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertEqual(payload["imported_count"], 1)
        self.assertEqual(payload["failed_count"], 0)
        self.assertEqual(len(payload["dashboard"]["positions"]), 1)
        self.assertEqual(len(payload["dashboard"]["watchlist"]), 1)
        self.assertEqual(payload["dashboard"]["watchlist_only"], [])

    def test_csv_can_import_watchlist_without_position_columns(self):
        response = self.client.post(
            "/api/portfolio/import",
            data={
                "target": "watchlist",
                "file": (io.BytesIO(b"symbol\nMSFT\n"), "watchlist.csv"),
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertEqual(payload["imported_count"], 1)
        self.assertEqual(len(payload["dashboard"]["watchlist_only"]), 1)


if __name__ == "__main__":
    unittest.main()
