"""Parse brokerage screenshots and files into normalized portfolio rows."""

from __future__ import annotations

import base64
import csv
import io
import json
import logging
import os
import re
import zipfile
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree


MAX_IMPORT_BYTES = 15 * 1024 * 1024
LOCAL_EXTENSIONS = {".csv", ".tsv", ".txt", ".json", ".xlsx"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
AI_FILE_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls"}
SUPPORTED_EXTENSIONS = LOCAL_EXTENSIONS | IMAGE_EXTENSIONS | AI_FILE_EXTENSIONS
logger = logging.getLogger(__name__)

FIELD_ALIASES = {
    "symbol": {
        "symbol", "ticker", "code", "代码", "证券代码", "股票代码", "基金代码", "资产代码",
    },
    "name": {"name", "asset", "security", "名称", "证券名称", "股票名称", "基金名称", "资产名称"},
    "quantity": {
        "quantity", "shares", "units", "position", "持仓", "持有", "数量", "份额",
        "持仓数量", "持有数量", "持有份额", "基金份额", "可用份额",
    },
    "cost_price": {
        "costprice", "averagecost", "avgcost", "price", "unitcost", "成本价", "持仓成本",
        "持仓成本价", "平均成本", "成本单价", "买入价", "成交价", "单位净值",
    },
    "asset_class": {"assetclass", "class", "资产大类", "资产类别", "品种", "类型"},
    "subclass": {"subclass", "markettype", "子类", "市场类型"},
    "occurred_at": {"occurredat", "date", "time", "日期", "时间", "交易日期", "持仓日期"},
    "currency": {"currency", "币种", "货币"},
}


def _header_key(value: Any) -> str:
    return re.sub(r"[\s_\-—（）()：:/.]", "", str(value or "")).casefold()


ALIAS_LOOKUP = {
    _header_key(alias): field
    for field, aliases in FIELD_ALIASES.items()
    for alias in aliases
}


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_symbol(value: Any) -> str:
    symbol = _clean_text(value).upper()
    if symbol.endswith(".0") and symbol[:-2].isdigit():
        symbol = symbol[:-2]
    return symbol


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _clean_text(value)
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace(",", "").replace("，", "")
    text = re.sub(r"[￥¥$€£\s份股元]", "", text)
    if text.endswith("%"):
        text = text[:-1]
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    number = float(match.group(0))
    return -number if negative else number


def _asset_class(value: Any) -> str:
    text = _clean_text(value).casefold()
    if text in {"stock", "股票", "证券", "a股", "港股", "美股"}:
        return "stock"
    if text in {"fund", "基金", "etf", "场内基金", "场外基金"}:
        return "fund"
    return ""


def _subclass(value: Any) -> str:
    text = _clean_text(value).casefold()
    mapping = {
        "cn": "cn", "a股": "cn", "沪市": "cn", "深市": "cn",
        "hk": "hk", "港股": "hk", "us": "us", "美股": "us",
        "exchange_traded": "exchange_traded", "etf": "exchange_traded", "场内基金": "exchange_traded",
        "otc": "otc", "场外基金": "otc",
    }
    return mapping.get(text, "")


def normalize_rows(rows: list[dict[str, Any]], target: str) -> list[dict[str, Any]]:
    """Map common Chinese/English brokerage headers to the import contract."""

    normalized: list[dict[str, Any]] = []
    for source in rows:
        mapped: dict[str, Any] = {}
        for key, value in source.items():
            canonical = ALIAS_LOOKUP.get(_header_key(key))
            if canonical and canonical not in mapped:
                mapped[canonical] = value
        symbol = _clean_symbol(mapped.get("symbol"))
        name = _clean_text(mapped.get("name"))
        if not symbol and not name:
            continue
        item = {
            "symbol": symbol,
            "name": name,
            "asset_class": _asset_class(mapped.get("asset_class")),
            "subclass": _subclass(mapped.get("subclass")),
            "currency": _clean_text(mapped.get("currency")).upper(),
            "occurred_at": _clean_text(mapped.get("occurred_at")),
        }
        if target == "holdings":
            quantity = _number(mapped.get("quantity"))
            # A holdings snapshot can include assets that have just been sold,
            # redeemed, or converted out. They are no longer current positions
            # and should not surface as failed imports.
            if quantity is not None and quantity <= 0:
                continue
            item["quantity"] = quantity
            item["cost_price"] = _number(mapped.get("cost_price"))
        normalized.append(item)
    return normalized


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("无法识别文件编码，请另存为 UTF-8 CSV 后重试")


def _parse_json(data: bytes) -> list[dict[str, Any]]:
    payload = json.loads(_decode_text(data))
    if isinstance(payload, dict):
        payload = payload.get("rows") or payload.get("items") or payload.get("positions")
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ValueError("JSON 需为对象数组，或包含 rows/items/positions 数组")
    return payload


def _parse_delimited(data: bytes, suffix: str) -> list[dict[str, Any]]:
    text = _decode_text(data)
    sample = text[:4096]
    delimiter = "\t" if suffix == ".tsv" else None
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",\t;|").delimiter
        except csv.Error:
            delimiter = ","
    return [dict(row) for row in csv.DictReader(io.StringIO(text), delimiter=delimiter)]


def _xlsx_cell_value(cell: ElementTree.Element, shared: list[str], namespace: dict[str, str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//main:t", namespace))
    value = cell.find("main:v", namespace)
    if value is None or value.text is None:
        return ""
    if cell_type == "s":
        try:
            return shared[int(value.text)]
        except (ValueError, IndexError):
            return ""
    return value.text


def _parse_xlsx(data: bytes) -> list[dict[str, Any]]:
    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise ValueError("Excel 文件已损坏或不是有效的 .xlsx 文件") from error
    with archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.text or "" for node in item.findall(".//main:t", namespace)) for item in root]
        sheet_names = sorted(
            name for name in archive.namelist()
            if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
        )
        if not sheet_names:
            raise ValueError("Excel 文件中没有可读取的工作表")
        rows: list[list[str]] = []
        root = ElementTree.fromstring(archive.read(sheet_names[0]))
        for row in root.findall(".//main:sheetData/main:row", namespace):
            values: dict[int, str] = {}
            for cell in row.findall("main:c", namespace):
                reference = cell.attrib.get("r", "A1")
                letters = re.match(r"[A-Z]+", reference)
                column = 0
                for character in (letters.group(0) if letters else "A"):
                    column = column * 26 + ord(character) - 64
                values[column - 1] = _xlsx_cell_value(cell, shared, namespace)
            if values:
                rows.append([values.get(index, "") for index in range(max(values) + 1)])
    if not rows:
        return []
    headers = rows[0]
    return [
        {headers[index]: value for index, value in enumerate(row) if index < len(headers)}
        for row in rows[1:]
    ]


def _json_from_model_output(text: str) -> list[dict[str, Any]]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    payload = json.loads(cleaned)
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("图片或文件中未识别出资产明细")
    return rows


def extract_rows_with_openai(filename: str, mime_type: str, data: bytes, target: str) -> list[dict[str, Any]]:
    """Use a vision-capable Responses model for screenshots and rich documents."""

    from openai import (
        APIConnectionError,
        AuthenticationError,
        BadRequestError,
        NotFoundError,
        OpenAI,
        RateLimitError,
    )

    suffix = Path(filename).suffix.lower()
    encoded = base64.b64encode(data).decode("ascii")
    if suffix in IMAGE_EXTENSIONS:
        attachment = {
            "type": "input_image",
            "image_url": f"data:{mime_type};base64,{encoded}",
            "detail": "high",
        }
    else:
        attachment = {
            "type": "input_file",
            "filename": Path(filename).name,
            "file_data": f"data:{mime_type};base64,{encoded}",
            "detail": "high" if suffix == ".pdf" else "auto",
        }
    required = "代码或名称、持有数量/份额、平均成本价" if target == "holdings" else "代码或名称"
    prompt = f"""从这份投资账户材料中提取要导入的资产。目标是{'持仓' if target == 'holdings' else '自选'}。
成功标准：逐行提取{required}；不要把总计、现金、盈亏统计或表头当成资产；看不清的值使用 null，不要猜测。
若材料中包含基金转换，只提取转换后的转入基金，不要提取已转出的原基金；以当前实际持有的基金名称、代码、份额和成本为准。
不要提取持有份额为 0、已清仓、已赎回或已转出的资产。代码可见时必须准确抄录，不要仅凭名称猜代码。
返回符合指定结构的资产行。"""
    row_properties = {
        "symbol": {"type": "string"},
        "name": {"type": "string"},
        "quantity": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "cost_price": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "asset_class": {"type": "string", "enum": ["stock", "fund", ""]},
        "subclass": {
            "type": "string",
            "enum": ["cn", "hk", "us", "exchange_traded", "otc", ""],
        },
        "currency": {"type": "string"},
        "occurred_at": {"type": "string"},
    }
    model = os.getenv("PORTFOLIO_IMPORT_MODEL", "gpt-5.6-luna")
    try:
        response = OpenAI().responses.create(
            model=model,
            reasoning={"effort": "none"},
            text={
                "verbosity": "low",
                "format": {
                    "type": "json_schema",
                    "name": "portfolio_import",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "rows": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": row_properties,
                                    "required": list(row_properties),
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": ["rows"],
                        "additionalProperties": False,
                    },
                },
            },
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    attachment,
                ],
            }],
        )
    except AuthenticationError as error:
        logger.exception("Portfolio import authentication failed")
        raise RuntimeError("OPENAI_API_KEY 无效或已失效，请更新配置后重启服务") from error
    except NotFoundError as error:
        logger.exception("Portfolio import model is unavailable: %s", model)
        raise RuntimeError(f"图片识别模型 {model} 不可用，请检查 PORTFOLIO_IMPORT_MODEL") from error
    except RateLimitError as error:
        logger.exception("Portfolio import was rate limited")
        raise RuntimeError("OpenAI API 配额不足或请求过于频繁，请稍后重试") from error
    except APIConnectionError as error:
        logger.exception("Portfolio import could not connect to OpenAI")
        raise RuntimeError("无法连接 OpenAI API，请检查网络或代理设置") from error
    except BadRequestError as error:
        logger.exception("Portfolio import request was rejected")
        raise RuntimeError("图片/文档请求未被模型接受，请确认文件清晰且格式受支持") from error
    except Exception as error:
        logger.exception("Unexpected portfolio import failure")
        raise RuntimeError("图片/文档识别失败，请查看服务日志后重试") from error
    return _json_from_model_output(response.output_text)


def parse_import_file(
    filename: str,
    mime_type: str,
    data: bytes,
    target: str,
    ai_extractor: Callable[[str, str, bytes, str], list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    if target not in {"holdings", "watchlist"}:
        raise ValueError("导入目标必须是持有或自选")
    if not filename or not data:
        raise ValueError("请选择非空文件")
    if len(data) > MAX_IMPORT_BYTES:
        raise ValueError("单个导入文件不能超过 15 MB")
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError("支持 PNG/JPG/WEBP/GIF、PDF、Word、CSV/TSV/TXT/JSON、XLS/XLSX")

    if suffix == ".json":
        rows = _parse_json(data)
    elif suffix in {".csv", ".tsv", ".txt"}:
        rows = _parse_delimited(data, suffix)
    elif suffix == ".xlsx":
        rows = _parse_xlsx(data)
    else:
        extractor = ai_extractor or extract_rows_with_openai
        rows = extractor(filename, mime_type or "application/octet-stream", data, target)

    normalized = normalize_rows(rows, target)
    if not normalized:
        raise ValueError("文件中没有识别出可导入的资产，请确认包含代码或名称")
    if len(normalized) > 500:
        raise ValueError("单次最多导入 500 条资产")
    return normalized
