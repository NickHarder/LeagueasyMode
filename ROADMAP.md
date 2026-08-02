# LeagueasyMode: Development Roadmap

## Phase 1: Core Engine (✅ Complete)

- [x] Persistent API Poller (Zero-lag TLS connection pool)
- [x] Event-Bus Architecture & Rule Engine
- [x] Auto-discovery for Rules & Champion configurations
- [x] Dynamic Manifest Generator
- [x] Spatial tracking via Kill Feed & Scoreboard Math

## Phase 2: UI & UX Polish (🚧 In Progress)

- [ ] Overhaul `index.html` for a modern, OBS-ready overlay.
- [ ] Add smooth CSS transitions for alerts sliding in/out.
- [ ] Implement TTS (Text-to-Speech) volume controls and toggle switches.
- [ ] Add distinct audio chimes based on alert priority (Info vs. Critical).

## Phase 3: The Champion Roster (Backlog)

- [ ] **Bruisers/Divers:** Vi, Jarvan IV, Xin Zhao (early gank thresholds)
- [ ] **AP Carries:** Nidalee, Lillia, Karthus (clear speed & greed mechanics)
- [ ] **Tanks:** Sejuani, Amumu, Zac (teamfight and CC tracking)

## Phase 4: Advanced Macro Rules (Backlog)

- [ ] **The Wave Reader:** Inferring lane priority based on enemy laner CS velocity.
- [ ] **Jungle Tracking 2.0:** Predicting enemy jungle pathing based on which lane leashed at 0:55.
- [ ] **Late Game Shotcaller:** Elder/Baron trade logic based on team player count.
