"""Standalone investment service — run separately on port 8081.

Start with:
    cd src/investment && python investment_app.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # expose src/ so investment_habits is importable

from flask import Flask, jsonify

from market_routes import market_blueprint
from market_service import service

app = Flask(__name__)
app.register_blueprint(market_blueprint)


@app.route("/api/habits/<habit_key>", methods=["DELETE"])
def dismiss_habit(habit_key: str):
    try:
        service.db.dismiss_investment_habit(habit_key)
    except Exception:
        return jsonify({"error": "Failed to dismiss habit"}), 500
    return jsonify({"ok": True})


@app.route("/api/habits")
def list_habits():
    try:
        return jsonify({"habits": service.db.list_investment_habits()})
    except Exception:
        return jsonify({"error": "Failed to load habits"}), 500


if __name__ == "__main__":
    from market_tracker import tracker

    tracker.start()
    app.run(
        host=os.getenv("INVESTMENT_HOST", "127.0.0.1"),
        port=int(os.getenv("INVESTMENT_PORT", "8081")),
        debug=os.getenv("THUMPER_DEBUG", "1") == "1",
        use_reloader=False,
    )
