# boty-agent

Code de Botti (Sam Botti) — agent IA de Botler 360 / Best of Tours.
Runtime : NanoClaw (Docker) sur Mac Mini M4.
Compte GWS : sam@bestoftours.co.uk

## Modules

- `modules/state.py` — Etat persistant (IDs traites, timestamps)
- `modules/gmail_poll.py` — Polling Gmail parametrable par compte
- `modules/chat_poll.py` — Polling Google Chat parametrable par compte/space
- `modules/listen.py` — Orchestrateur Mode Ecoute

## Credentials GWS (sur le container)

- yacine@ : `/home/node/.config/gws/`
- sam@    : `/home/node/.config/gws/accounts/sam/`
- eline@  : `/home/node/.config/gws/accounts/eline/` (a creer)
- alex@   : `/home/node/.config/gws/accounts/alex/` (a creer)

## Usage

```bash
python3 modules/listen.py all --account yacine
python3 modules/listen.py gmail --account yacine --summary
python3 modules/listen.py chat --account sam
```
