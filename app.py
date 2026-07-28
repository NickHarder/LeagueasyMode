import socket
import threading
import time
from enum import IntEnum
from typing import Any, TypedDict, cast

import requests
import urllib3
from flask import Flask, jsonify, render_template, request
from flask.wrappers import Response
from requests.adapters import HTTPAdapter

# Suppress insecure request warnings since the League API uses local self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# =====================================================================
# CONFIGURATION
# =====================================================================

HYPER_CARRIES = {"Kayle", "Kassadin", "Smolder", "Vayne", "Vladimir"}
COMBAT_SPELLS = {"Ignite", "Exhaust", "Barrier"}
PORT = 5050

# =====================================================================
# TYPES & GLOBAL STATE
# =====================================================================

class AlertPriority(IntEnum):
    CRITICAL = 1
    TACTICAL = 2
    INFO = 3

class AlertMsg(TypedDict):
    id: float
    priority: int
    title: str
    text: str
    speech: str
    sound: str

class GlobalState(TypedDict):
    connected: bool
    game_time: float
    my_name: str
    my_role: str
    my_level: int
    my_opponent: dict[str, Any] | None
    enemy_jg_alive: bool
    enemy_jg_level: int
    next_dragon_time: float
    next_baron_time: float

global_state: GlobalState = {
    "connected": False,
    "game_time": 0.0,
    "my_name": "",
    "my_role": "UNKNOWN",
    "my_level": 1,
    "my_opponent": None,
    "enemy_jg_alive": True,
    "enemy_jg_level": 1,
    "next_dragon_time": 300.0,
    "next_baron_time": 1200.0,
}

alerts_queue: list[AlertMsg] = []
alerts_lock = threading.Lock()

def push_alert(priority: AlertPriority, title: str, text: str, speech: str = "", sound: str = "chime") -> None:
    if not speech:
        speech = text
    with alerts_lock:
        alerts_queue.append({
            "id": time.time(),
            "priority": int(priority),
            "title": title,
            "text": text,
            "speech": speech,
            "sound": sound
        })

# =====================================================================
# ENGINE & DATA SCRAPING
# =====================================================================

class GameContext:
    def __init__(self) -> None:
        self.is_initialized: bool = False 
        self.session = requests.Session()
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
        self.session.mount("https://", adapter)
        
        self.url_active = "https://127.0.0.1:2999/liveclientdata/activeplayer"
        self.url_players = "https://127.0.0.1:2999/liveclientdata/playerlist"
        self.url_events = "https://127.0.0.1:2999/liveclientdata/eventdata"
        self.url_game = "https://127.0.0.1:2999/liveclientdata/gamestats"

    def fetch_all(self) -> bool:
        try:
            # Slightly higher timeout to prevent micro-stutter disconnects
            r_active = self.session.get(self.url_active, verify=False, timeout=0.5)
            r_players = self.session.get(self.url_players, verify=False, timeout=0.5)
            r_events = self.session.get(self.url_events, verify=False, timeout=0.5)
            r_game = self.session.get(self.url_game, verify=False, timeout=0.5)

            if all(r.status_code == 200 for r in [r_active, r_players, r_events, r_game]):
                self.update(
                    cast(dict[str, Any], r_active.json()), 
                    cast(list[dict[str, Any]], r_players.json()), 
                    cast(dict[str, Any], r_events.json()), 
                    cast(dict[str, Any], r_game.json())
                )
                return True
        except requests.exceptions.RequestException:
            pass
        return False

    def update(
        self, 
        raw_active: dict[str, Any], 
        raw_players: list[dict[str, Any]], 
        raw_events: dict[str, Any], 
        raw_game: dict[str, Any]
    ) -> None:
        global global_state
        global_state["connected"] = True
        global_state["game_time"] = float(raw_game.get("gameTime", 0.0))
        global_state["my_name"] = raw_active.get("summonerName", "")
        
        my_team = None

        for p in raw_players:
            if p.get("summonerName") == global_state["my_name"]:
                my_team = p.get("team")
                pos = p.get("position", "")
                global_state["my_role"] = pos if pos else "JUNGLE"
                global_state["my_level"] = int(p.get("level", 1))
                break

        global_state["my_opponent"] = None
        enemy_jg = None
        for p in raw_players:
            if p.get("team") != my_team and p.get("team") is not None:
                if p.get("position") == global_state["my_role"]:
                    global_state["my_opponent"] = p
                if p.get("position") == "JUNGLE":
                    enemy_jg = p

        if enemy_jg:
            global_state["enemy_jg_alive"] = not bool(enemy_jg.get("isDead", False))
            global_state["enemy_jg_level"] = int(enemy_jg.get("level", 1))

        t = global_state["game_time"]
        events = raw_events.get("Events", [])
        for e in events:
            name = e.get("EventName")
            etime = e.get("EventTime", t)
            if name == "DragonKill":
                global_state["next_dragon_time"] = etime + 300.0
            elif name == "BaronKill":
                global_state["next_baron_time"] = etime + 180.0

        if not self.is_initialized:
            self.is_initialized = True
            print(f"[SYSTEM] Telemetry Engine Synced at {t}s.")

def game_loop() -> None:
    ctx = GameContext()
    triggered_events: set[str] = set()

    while True:
        if ctx.fetch_all():
            t = global_state["game_time"]
            opp = global_state["my_opponent"]
            my_lvl = global_state["my_level"]
            my_role = global_state["my_role"]

            # RESET LOGIC: If game time is less than 5 seconds, it's a brand new game.
            if t < 5.0 and len(triggered_events) > 0:
                triggered_events.clear()
                with alerts_lock:
                    alerts_queue.clear()
                print("[SYSTEM] New match detected. Wiped alert history.")

            # 1. PRE-MATCH CHEESE CHECK
            if 15.0 <= t <= 20.0 and "cheese" not in triggered_events and opp:
                triggered_events.add("cheese")
                spells = opp.get("summonerSpells", {})
                s1 = spells.get("summonerSpellOne", {}).get("displayName", "")
                s2 = spells.get("summonerSpellTwo", {}).get("displayName", "")
                if any(sp in COMBAT_SPELLS for sp in [s1, s2]):
                    push_alert(AlertPriority.CRITICAL, "CHEESE RISK", "Opponent has combat summoners!", sound="alert")

            # 2. LEVEL 2/3 PRIORITY TRACKER
            if opp:
                opp_lvl = int(opp.get("level", 1))
                champ = opp.get("championName", "Opponent")
                
                if opp_lvl == 2 and my_lvl == 1 and "lvl2" not in triggered_events:
                    triggered_events.add("lvl2")
                    push_alert(AlertPriority.CRITICAL, "LEVEL DISADVANTAGE", f"{champ} hit Level 2 first! Back off.", "Warning, opponent is level 2.", sound="alert")
                
                if opp_lvl == 3 and my_lvl == 2 and "lvl3" not in triggered_events:
                    triggered_events.add("lvl3")
                    push_alert(AlertPriority.CRITICAL, "LEVEL DISADVANTAGE", f"{champ} hit Level 3 first! Back off.", "Warning, opponent is level 3.", sound="alert")

            # 3. SCUTTLE & EARLY VISION
            if 155.0 <= t <= 160.0 and "scuttle" not in triggered_events:
                triggered_events.add("scuttle")
                push_alert(AlertPriority.TACTICAL, "SCUTTLE PREP", "Scuttles spawn at 2:55.", "Scuttles spawning in 20 seconds.", sound="chime")

            if 170.0 <= t <= 175.0 and "wards" not in triggered_events:
                triggered_events.add("wards")
                push_alert(AlertPriority.INFO, "VISION", "Level 1 Wards expiring. Gank windows open.", "Early wards expiring.", sound="chime")

            # 4. CANNON WAVE RECALL WINDOWS
            if my_role in {"TOP", "MID", "BOTTOM", "SUPPORT"} and 0 < t < 900:
                cannon_idx = int((t - 20) / 90) 
                next_alert_time = 110 + (cannon_idx * 90)
                event_tag = f"cannon_{cannon_idx}"
                
                if next_alert_time <= t < (next_alert_time + 5) and event_tag not in triggered_events:
                    triggered_events.add(event_tag)
                    push_alert(AlertPriority.INFO, "RECALL WINDOW", "Cannon wave spawns in 15s. Crash and base.", "Optimal recall window opening.", sound="chime")

            # 5. HARD 8s RECALL DEADLINE
            if opp:
                is_dead = bool(opp.get("isDead", False))
                timer = float(opp.get("respawnTimer", 0.0))
                
                if is_dead and 0 < timer <= 8.0:
                    if "recall" not in triggered_events:
                        triggered_events.add("recall")
                        push_alert(AlertPriority.CRITICAL, "RECALL DEADLINE", "Opponent respawning in 8s!", "Recall deadline.", sound="alert")
                elif not is_dead:
                    triggered_events.discard("recall")

            # 6. HYPER-CARRY LEVEL 16 TIMEBOMB
            if opp:
                name = opp.get("summonerName", "")
                champ = opp.get("championName", "")
                lvl = int(opp.get("level", 1))
                event_tag = f"lvl16_{name}"
                
                if lvl >= 16 and event_tag not in triggered_events and champ in HYPER_CARRIES:
                    triggered_events.add(event_tag)
                    push_alert(AlertPriority.CRITICAL, "LATE GAME THREAT", f"Hyper-carry {champ} hit Level 16!", sound="alert")

            # 7. OBJECTIVE VISION PREP
            drag_time = global_state["next_dragon_time"]
            drag120_tag = f"drag120_{drag_time}"
            drag60_tag = f"drag60_{drag_time}"
            
            # Only trigger if the game has progressed past 5 minutes (300s default spawn)
            if t > 60:
                if 0 < (drag_time - t) <= 120.5 and drag120_tag not in triggered_events:
                    triggered_events.add(drag120_tag)
                    push_alert(AlertPriority.TACTICAL, "VISION PREP", "Dragon in 2 mins. Buy wards.", "Dragon in 2 minutes.", sound="chime")

                if 0 < (drag_time - t) <= 60.5 and drag60_tag not in triggered_events:
                    triggered_events.add(drag60_tag)
                    cf = ". Enemy JG Alive!" if global_state["enemy_jg_alive"] else ". Enemy JG Dead."
                    push_alert(AlertPriority.CRITICAL, "OBJECTIVE SPAWN", f"Dragon in 60s{cf}", f"Dragon in 1 minute{cf}", sound="alert")

        else:
            global_state["connected"] = False
            # WE NO LONGER CLEAR TRIGGERED EVENTS HERE.
            # If the client stutters, it will silently wait for the next frame.
            ctx = GameContext()

        time.sleep(0.1)

# =====================================================================
# FLASK WEB ROUTES
# =====================================================================

@app.route("/")
def index() -> str:
    return render_template("index.html")

@app.route("/api/state")
def get_state() -> Response:
    client_last_id = float(request.args.get("last_alert_id", 0.0))
    
    with alerts_lock:
        new_alerts = [a for a in alerts_queue if a["id"] > client_last_id]

    return jsonify({
        "state": global_state,
        "alerts": new_alerts
    })

def get_mac_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = str(s.getsockname()[0])
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

if __name__ == "__main__":
    ip_address = get_mac_local_ip()
    print("=" * 50)
    print("[SERVICE] LeagueasyMode Telemetry Server Active")
    print(f"[NETWORK] Listening on LAN interface: http://{ip_address}:{PORT}")
    print("=" * 50)

    t = threading.Thread(target=game_loop, daemon=True)
    t.start()

    app.run(host="0.0.0.0", port=PORT, debug=False)