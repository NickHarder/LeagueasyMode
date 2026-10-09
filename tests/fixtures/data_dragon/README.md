These files stand in for Riot's Data Dragon (`ddragon.leagueoflegends.com`) in the tests. They
have Data Dragon's shape (`/api/versions.json`, and `/cdn/<version>/data/en_US/championFull.json`,
`item.json` and `summoner.json`), cut to the champions, items and spells the tests use; the
numbers are written by hand and are not this patch's. On 2026-10-09 the engine's reading was
checked against the real files of patch 16.20.1: every champion, item and summoner spell parses,
and the numbers read match Data Dragon's, but for one gap of Data Dragon's own. Since 16.5.1 it
gives every champion an attack damage growth of 0, while the game's data still has it (Ahri's 3 a
level); the engine borrows it from the newest older patch that has it, 16.4.1
(`champions_without_growth` in `tests/data_dragon_fixtures.py` stands in for such a file).
