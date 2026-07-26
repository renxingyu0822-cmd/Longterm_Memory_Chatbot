import io
import sys
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from portfolio_import import extract_rows_with_openai, parse_import_file  # noqa: E402


class PortfolioImportParserTests(unittest.TestCase):
    def test_chinese_csv_headers_are_normalized(self):
        rows = parse_import_file(
            "positions.csv",
            "text/csv",
            "证券代码,证券名称,持有份额,持仓成本价\n005827,易方达蓝筹精选混合,1234.5,1.8234\n".encode(),
            "holdings",
        )

        self.assertEqual(rows[0]["symbol"], "005827")
        self.assertEqual(rows[0]["quantity"], 1234.5)
        self.assertEqual(rows[0]["cost_price"], 1.8234)

    def test_json_watchlist_only_needs_symbol_or_name(self):
        rows = parse_import_file(
            "watchlist.json",
            "application/json",
            b'{"items":[{"ticker":"NVDA"},{"name":"Microsoft"}]}',
            "watchlist",
        )

        self.assertEqual([row["symbol"] for row in rows], ["NVDA", ""])
        self.assertEqual(rows[1]["name"], "Microsoft")

    def test_xlsx_first_sheet_is_read_without_extra_dependency(self):
        shared_strings = """<?xml version="1.0" encoding="UTF-8"?>
        <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <si><t>代码</t></si><si><t>数量</t></si><si><t>成本价</t></si><si><t>AAPL</t></si>
        </sst>"""
        worksheet = """<?xml version="1.0" encoding="UTF-8"?>
        <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
          <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c></row>
          <row r="2"><c r="A2" t="s"><v>3</v></c><c r="B2"><v>2</v></c><c r="C2"><v>190.5</v></c></row>
        </sheetData></worksheet>"""
        content = io.BytesIO()
        with zipfile.ZipFile(content, "w") as archive:
            archive.writestr("xl/sharedStrings.xml", shared_strings)
            archive.writestr("xl/worksheets/sheet1.xml", worksheet)

        rows = parse_import_file(
            "positions.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            content.getvalue(),
            "holdings",
        )

        self.assertEqual(rows[0]["symbol"], "AAPL")
        self.assertEqual(rows[0]["quantity"], 2)
        self.assertEqual(rows[0]["cost_price"], 190.5)

    def test_image_extractor_can_be_injected(self):
        calls = []

        def extractor(filename, mime_type, data, target):
            calls.append((filename, mime_type, data, target))
            return [{"symbol": "0700", "quantity": "100", "cost_price": "350.2"}]

        rows = parse_import_file(
            "account.png",
            "image/png",
            b"not-a-real-image",
            "holdings",
            ai_extractor=extractor,
        )

        self.assertEqual(calls[0][3], "holdings")
        self.assertEqual(rows[0]["quantity"], 100)

    def test_converted_out_zero_position_is_not_imported(self):
        def extractor(filename, mime_type, data, target):
            return [
                {
                    "symbol": "161725",
                    "name": "招商中证白酒指数(LOF)A",
                    "quantity": 0,
                    "cost_price": 0,
                },
                {
                    "symbol": "022364",
                    "name": "永赢科技智选混合发起A",
                    "quantity": 123.45,
                    "cost_price": 1.08,
                },
            ]

        rows = parse_import_file(
            "conversion.png",
            "image/png",
            b"not-a-real-image",
            "holdings",
            ai_extractor=extractor,
        )

        self.assertEqual([row["symbol"] for row in rows], ["022364"])

    @patch("openai.OpenAI")
    def test_openai_image_request_uses_high_detail_and_structured_output(self, client_class):
        client_class.return_value.responses.create.return_value = SimpleNamespace(
            output_text='{"rows":[{"symbol":"AAPL","name":"Apple","quantity":2,"cost_price":190,"asset_class":"stock","subclass":"us","currency":"USD","occurred_at":""}]}'
        )

        rows = extract_rows_with_openai("account.png", "image/png", b"image", "holdings")

        request = client_class.return_value.responses.create.call_args.kwargs
        self.assertEqual(request["model"], "gpt-5.6-luna")
        self.assertEqual(request["reasoning"], {"effort": "none"})
        self.assertEqual(request["input"][0]["content"][1]["detail"], "high")
        self.assertEqual(request["text"]["format"]["type"], "json_schema")
        self.assertIn("只提取转换后的转入基金", request["input"][0]["content"][0]["text"])
        self.assertEqual(rows[0]["symbol"], "AAPL")

    @patch("openai.OpenAI")
    def test_openai_connection_error_is_actionable(self, client_class):
        from openai import APIConnectionError

        client_class.return_value.responses.create.side_effect = APIConnectionError(
            request=SimpleNamespace(method="POST", url="https://api.openai.com/v1/responses")
        )

        with self.assertRaisesRegex(RuntimeError, "无法连接 OpenAI API"):
            extract_rows_with_openai("account.png", "image/png", b"image", "holdings")


if __name__ == "__main__":
    unittest.main()
