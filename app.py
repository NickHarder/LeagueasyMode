import socket
import threading
import time

from flask import Flask, jsonify, render_template, request
from flask.wrappers import Response

from engine.event_bus import EventBus
from engine.poller import GameContext, global_state
from rules import load_all_rules

app = Flask(__name__)
PORT = 5050

bus = EventBus()
load_all_rules(bus)

alerts_queue = []
alerts_lock = threading.Lock()


def game_loop() -> None:
    """The core 10ms loop. Polls data, updates state, and fires rules."""
    ctx = GameContext()

    while True:
        if ctx.fetch_all():
            new_alerts = bus.evaluate_all(global_state)

            if new_alerts:
                with alerts_lock:
                    alerts_queue.extend(new_alerts)
        else:
            # If client disconnects/stutters, wait a bit before retrying
            time.sleep(1.0)

        time.sleep(0.1)


# ======================================================================================
# FLASK WEB ROUTES
# ======================================================================================


@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/api/state")
def get_state() -> Response:
    client_last_id = float(request.args.get("last_alert_id", 0.0))

    with alerts_lock:
        # Only send alerts the Pi hasn't played yet
        pending_alerts = [a for a in alerts_queue if a["id"] > client_last_id]

    return jsonify({"state": global_state, "alerts": pending_alerts})


def get_mac_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = str(s.getsockname()[0])
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


if __name__ == "__main__":
    ip_address = get_mac_local_ip()
    print("=" * 50)
    print("[SERVICE] LeagueasyMode Telemetry Server Active")
    print(f"[NETWORK] Listening on LAN interface: http://{ip_address}:{PORT}")
    print("=" * 50)

    # Start the backend polling loop in a background thread
    t = threading.Thread(target=game_loop, daemon=True)
    t.start()

    # Disable debug mode to prevent the Flask reloader from spawning duplicate threads
    app.run(host="0.0.0.0", port=PORT, debug=False)
