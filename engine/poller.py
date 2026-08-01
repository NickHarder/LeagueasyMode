from typing import Any, TypedDict, cast

import requests
import urllib3
from requests.adapters import HTTPAdapter

# Suppress insecure request warnings since the League API uses local self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ======================================================================================
# STATE SCHEMA
# ======================================================================================


class GlobalState(TypedDict):
    connected: bool
    game_time: float
    my_name: str
    my_champion: str
    my_role: str
    my_level: int
    my_gold: int
    my_cs: int
    my_items: set[str]
    my_opponent: dict[str, Any] | None
    enemy_jg_alive: bool
    enemy_jg_level: int
    enemy_jg_cs: int
    enemy_jg_kills: int
    enemy_jg_assists: int
    next_dragon_time: float
    next_baron_time: float


global_state: GlobalState = {
    "connected": False,
    "game_time": 0.0,
    "my_name": "",
    "my_champion": "",
    "my_role": "UNKNOWN",
    "my_level": 1,
    "my_gold": 0,
    "my_cs": 0,
    "my_items": set(),
    "my_opponent": None,
    "enemy_jg_alive": True,
    "enemy_jg_level": 1,
    "enemy_jg_cs": 0,
    "enemy_jg_kills": 0,
    "enemy_jg_assists": 0,
    "next_dragon_time": 300.0,
    "next_baron_time": 1200.0,
}

# ======================================================================================
# DATA SCRAPER
# ======================================================================================


class GameContext:
    def __init__(self) -> None:
        self.is_initialized: bool = False
        self.session = requests.Session()

        # Maintains a persistent connection pool to eliminate 800ms TLS handshake lag
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
        self.session.mount("https://", adapter)

        self.url_active = "https://127.0.0.1:2999/liveclientdata/activeplayer"
        self.url_players = "https://127.0.0.1:2999/liveclientdata/playerlist"
        self.url_events = "https://127.0.0.1:2999/liveclientdata/eventdata"
        self.url_game = "https://127.0.0.1:2999/liveclientdata/gamestats"

    def fetch_all(self) -> bool:
        """Hits the local Riot API and triggers a state update if successful."""
        try:
            # 0.5s timeout prevents micro-stutters if the game client temporarily hangs
            r_active = self.session.get(self.url_active, verify=False, timeout=0.5)
            r_players = self.session.get(self.url_players, verify=False, timeout=0.5)
            r_events = self.session.get(self.url_events, verify=False, timeout=0.5)
            r_game = self.session.get(self.url_game, verify=False, timeout=0.5)

            if all(r.status_code == 200 for r in [r_active, r_players, r_events, r_game]):
                self.update(
                    cast(dict[str, Any], r_active.json()),
                    cast(list[dict[str, Any]], r_players.json()),
                    cast(dict[str, Any], r_events.json()),
                    cast(dict[str, Any], r_game.json()),
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
        raw_game: dict[str, Any],
    ) -> None:
        """Parses the raw JSON payloads into our streamlined GlobalState dictionary."""
        global global_state

        global_state["connected"] = True
        global_state["game_time"] = float(raw_game.get("gameTime", 0.0))
        global_state["my_name"] = raw_active.get("summonerName", "")
        global_state["my_gold"] = int(raw_active.get("currentGold", 0))

        my_team = None

        # 1. Identify the active player
        for p in raw_players:
            if p.get("summonerName") == global_state["my_name"]:
                my_team = p.get("team")
                pos = p.get("position", "")
                global_state["my_role"] = pos if pos else "JUNGLE"
                global_state["my_level"] = int(p.get("level", 1))
                global_state["my_champion"] = p.get("championName", "")

                scores = p.get("scores", {})
                global_state["my_cs"] = int(scores.get("creepScore", 0))

                raw_items = p.get("items", [])
                global_state["my_items"] = {i.get("displayName", "") for i in raw_items}
                break

        # 2. Identify opponents
        global_state["my_opponent"] = None
        enemy_jg = None

        for p in raw_players:
            if p.get("team") != my_team and p.get("team") is not None:
                if p.get("position") == global_state["my_role"]:
                    global_state["my_opponent"] = p

                if p.get("position") == "JUNGLE":
                    enemy_jg = p

        # 3. Track enemy jungler status
        if enemy_jg:
            global_state["enemy_jg_alive"] = not bool(enemy_jg.get("isDead", False))
            global_state["enemy_jg_level"] = int(enemy_jg.get("level", 1))

            scores = enemy_jg.get("scores", {})
            global_state["enemy_jg_cs"] = int(scores.get("creepScore", 0))
            global_state["enemy_jg_kills"] = int(scores.get("kills", 0))
            global_state["enemy_jg_assists"] = int(scores.get("assists", 0))

        # 4. Parse objective timers
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
