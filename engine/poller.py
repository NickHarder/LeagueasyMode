from typing import Any, TypedDict, cast

import requests
import urllib3
from requests.adapters import HTTPAdapter

# Suppress insecure request warnings since the League API uses local self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ======================================================================================
# CONSTANTS
# ======================================================================================

FIRST_DRAGON_TIME = 300.0
FIRST_BARON_TIME = 1200.0

DRAGON_RESPAWN = 300.0
ELDER_RESPAWN = 360.0
BARON_RESPAWN = 180.0

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
    my_summoner_spells: list[str]
    my_items: set[str]
    my_opponent: dict[str, Any] | None
    player_positions: dict[str, str]
    enemy_team_stats: list[dict[str, Any]]
    enemy_jg_last_seen_role: str
    enemy_jg_last_seen_time: float
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
    "my_summoner_spells": [],
    "my_items": set(),
    "my_opponent": None,
    "player_positions": {},
    "enemy_team_stats": [],
    "enemy_jg_last_seen_role": "UNKNOWN",
    "enemy_jg_last_seen_time": 0.0,
    "enemy_jg_alive": True,
    "enemy_jg_level": 1,
    "enemy_jg_cs": 0,
    "enemy_jg_kills": 0,
    "enemy_jg_assists": 0,
    "next_dragon_time": FIRST_DRAGON_TIME,
    "next_baron_time": FIRST_BARON_TIME,
}

# ======================================================================================
# DATA SCRAPER
# ======================================================================================


class GameContext:
    def __init__(self) -> None:
        self.is_initialized: bool = False
        self.session = requests.Session()

        # Maintains a persistent connection pool to eliminate TLS handshake lag
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
        self.session.mount("https://", adapter)

        BASE_URL = "https://127.0.0.1:2999/liveclientdata"
        self.url_active = f"{BASE_URL}/activeplayer"
        self.url_players = f"{BASE_URL}/playerlist"
        self.url_events = f"{BASE_URL}/eventdata"
        self.url_game = f"{BASE_URL}/gamestats"

    def fetch_all(self) -> bool:
        """Hits the local Riot API and triggers a state update if successful."""
        try:
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

        # Mark disconnected if requests fail
        global_state["connected"] = False
        return False

    def update(
        self,
        raw_active: dict[str, Any],
        raw_players: list[dict[str, Any]],
        raw_events: dict[str, Any],
        raw_game: dict[str, Any],
    ) -> None:
        """Master orchestrator for parsing telemetry payloads."""

        t = float(raw_game.get("gameTime", 0.0))
        my_name = raw_active.get("summonerName", "")

        global_state["connected"] = True
        global_state["game_time"] = t
        global_state["my_name"] = my_name
        global_state["my_gold"] = int(float(raw_active.get("currentGold", 0)))

        self._update_spells(raw_active)
        my_team = self._update_active_context(raw_players, my_name)
        enemy_jg_name, positions = self._update_players(raw_players, my_name, my_team)
        self._update_events(raw_events, t, enemy_jg_name, positions)

        if not self.is_initialized:
            self.is_initialized = True
            print(f"[SYSTEM] Telemetry Engine Synced at {t:.1f}s.")

    # ----------------------------------------------------------------------------------
    # PRIVATE PARSING MODULES
    # ----------------------------------------------------------------------------------

    def _update_spells(self, raw_active: dict[str, Any]) -> None:
        spells = raw_active.get("summonerSpells", {})
        global_state["my_summoner_spells"] = [
            spell_data.get("displayName", "")
            for spell_data in spells.values()
            if isinstance(spell_data, dict) and "displayName" in spell_data
        ]

    def _update_active_context(self, raw_players: list[dict[str, Any]], my_name: str) -> str | None:
        active_entry = next((p for p in raw_players if p.get("summonerName") == my_name), None)

        my_team = active_entry.get("team") if active_entry else None
        my_pos = active_entry.get("position", "") if active_entry else ""
        global_state["my_role"] = my_pos or "UNKNOWN"

        return my_team

    def _update_players(
        self, raw_players: list[dict[str, Any]], my_name: str, my_team: str | None
    ) -> tuple[str, dict[str, str]]:

        positions: dict[str, str] = {}
        enemy_jg: dict[str, Any] | None = None
        enemy_jg_name: str = ""
        global_state["my_opponent"] = None

        enemy_team = []

        for p in raw_players:
            name = p.get("summonerName", "")
            pos = p.get("position", "UNKNOWN")
            team = p.get("team")
            positions[name] = pos

            # 1. Self Stats
            if name == my_name:
                global_state["my_level"] = int(float(p.get("level", 1)))
                global_state["my_champion"] = p.get("championName", "")

                scores = p.get("scores", {})
                global_state["my_cs"] = int(float(scores.get("creepScore", 0)))

                raw_items = p.get("items", [])
                global_state["my_items"] = {i.get("displayName", "") for i in raw_items if i.get("displayName")}
                continue

            # 2. Opponent Stats
            if my_team is not None and team != my_team:
                enemy_team.append(p)

                # Strictly map lane opponent only if Riot has assigned roles
                if global_state["my_role"] != "UNKNOWN" and pos == global_state["my_role"]:
                    global_state["my_opponent"] = p

                if pos == "JUNGLE":
                    enemy_jg = p
                    enemy_jg_name = name

        global_state["player_positions"] = positions
        global_state["enemy_team_stats"] = enemy_team

        # 3. Enemy Jungler Extraction
        if enemy_jg is not None:
            global_state["enemy_jg_alive"] = not bool(enemy_jg.get("isDead", False))
            global_state["enemy_jg_level"] = int(float(enemy_jg.get("level", 1)))

            scores = enemy_jg.get("scores", {})
            global_state["enemy_jg_cs"] = int(float(scores.get("creepScore", 0)))
            global_state["enemy_jg_kills"] = int(float(scores.get("kills", 0)))
            global_state["enemy_jg_assists"] = int(float(scores.get("assists", 0)))

        return enemy_jg_name, positions

    def _update_events(
        self, raw_events: dict[str, Any], t: float, enemy_jg_name: str, positions: dict[str, str]
    ) -> None:

        events = raw_events.get("Events")
        if not isinstance(events, list):
            events = []

        for e in events:
            event_name = e.get("EventName")
            etime = float(e.get("EventTime", t))

            # Champion Kill Feed (Spatial Awareness)
            if event_name == "ChampionKill":
                killer = e.get("KillerName", "")
                victim = e.get("VictimName", "")
                assisters = e.get("Assisters", [])

                if enemy_jg_name and (enemy_jg_name == killer or enemy_jg_name in assisters or enemy_jg_name == victim):
                    target_name = victim if enemy_jg_name != victim else killer
                    location_role = positions.get(target_name, "UNKNOWN")

                    global_state["enemy_jg_last_seen_role"] = location_role
                    global_state["enemy_jg_last_seen_time"] = etime

            # Objective Timers
            elif event_name == "DragonKill":
                dragon_type = e.get("DragonType", "")
                respawn_delay = ELDER_RESPAWN if dragon_type == "Elder" else DRAGON_RESPAWN
                global_state["next_dragon_time"] = etime + respawn_delay

            elif event_name == "BaronKill":
                global_state["next_baron_time"] = etime + BARON_RESPAWN
