"""Flask routes for the local investment workspace."""

from __future__ import annotations

import json
import time

from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context

from market_db import DEFAULT_OWNER
from market_service import service


market_blueprint = Blueprint("market", __name__)


def _json_body() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")
    return payload


@market_blueprint.route("/market")
def market_page():
    return render_template("market.html", lang=request.args.get("lang", "zh"))


@market_blueprint.route("/market/asset/<int:asset_id>")
def asset_page(asset_id: int):
    if not service.db.get_asset(asset_id):
        return render_template("market_not_found.html"), 404
    return render_template("asset_detail.html", asset_id=asset_id, lang=request.args.get("lang", "zh"))


@market_blueprint.route("/api/market/search")
def search_assets():
    try:
        results = service.search(
            request.args.get("q", ""),
            request.args.get("asset_class") or None,
            request.args.get("subclass") or None,
        )
        return jsonify({"results": results})
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception:
        return jsonify({"error": "行情搜索暂时不可用"}), 502


@market_blueprint.route("/api/market/dashboard")
def market_dashboard():
    return jsonify(service.dashboard(DEFAULT_OWNER, refresh_missing=True))


@market_blueprint.route("/api/market/watchlist", methods=["GET", "POST"])
def watchlist():
    if request.method == "GET":
        return jsonify({"items": service.db.list_watchlist(DEFAULT_OWNER)})
    try:
        item = service.add_watchlist(_json_body(), DEFAULT_OWNER)
        return jsonify({"item": item}), 201
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception:
        return jsonify({"error": "无法添加自选，请检查行情连接"}), 502


@market_blueprint.route("/api/market/watchlist/<int:asset_id>", methods=["DELETE"])
def remove_watchlist(asset_id: int):
    service.db.remove_watchlist(asset_id, DEFAULT_OWNER)
    return jsonify({"ok": True})


@market_blueprint.route("/api/market/assets/<int:asset_id>")
def asset_detail(asset_id: int):
    try:
        refresh = request.args.get("refresh") == "1"
        return jsonify(service.get_asset_detail(asset_id, refresh=refresh))
    except ValueError as error:
        return jsonify({"error": str(error)}), 404
    except Exception:
        return jsonify({"error": "行情或分析暂时不可用"}), 502


@market_blueprint.route("/api/market/assets/<int:asset_id>/refresh", methods=["POST"])
def refresh_asset(asset_id: int):
    try:
        return jsonify(service.refresh_asset(asset_id, force=True))
    except ValueError as error:
        return jsonify({"error": str(error)}), 404
    except Exception:
        return jsonify({"error": "刷新失败，请稍后重试"}), 502


@market_blueprint.route("/api/portfolio")
def portfolio():
    return jsonify(service.dashboard(DEFAULT_OWNER, refresh_missing=True))


@market_blueprint.route("/api/portfolio/summary")
def portfolio_summary():
    return jsonify(service.db.portfolio_summary(DEFAULT_OWNER))


@market_blueprint.route("/api/portfolio/transactions", methods=["GET", "POST"])
def transactions():
    if request.method == "GET":
        asset_id = request.args.get("asset_id", type=int)
        return jsonify({"items": service.db.list_transactions(DEFAULT_OWNER, asset_id)})
    try:
        transaction = service.add_transaction(_json_body(), DEFAULT_OWNER)
        dashboard = service.dashboard(DEFAULT_OWNER, refresh_missing=False)
        return jsonify({"transaction": transaction, "dashboard": dashboard}), 201
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception:
        return jsonify({"error": "无法保存交易"}), 500


@market_blueprint.route("/api/market/stream")
def market_stream():
    @stream_with_context
    def events():
        while True:
            payload = {
                "type": "market_update",
                "assets": service.refresh_tracked(DEFAULT_OWNER),
                "dashboard": service.dashboard(DEFAULT_OWNER, refresh_missing=False),
            }
            yield f"event: market_update\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            time.sleep(30)

    return Response(
        events(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

