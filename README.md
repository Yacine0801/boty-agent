# boty-agent

Code des agents IA Botler 360 / Best of Tours.
Runtime : NanoClaw (Docker) sur Mac Mini M4.

## Architecture

Spawner un agent = creer `agents/{nom}/config.json`. Zero modification de code.

```
agents/
  boty/config.json    # Agent Botti (sam@bestoftours.co.uk)
  eline/config.json   # Copier boty, changer les valeurs
modules/
  agent_config.py     # Loader config (--config ou AGENT_CONFIG_PATH)
  state.py            # Etat persistant (IDs traites, timestamps)
  gmail_poll.py       # Polling Gmail
  chat_poll.py        # Polling Google Chat
  listen.py           # Orchestrateur Mode Ecoute
  heartbeat.js        # Heartbeat Firestore nodes_status
```

## Usage

```bash
# Toujours passer --config ou definir AGENT_CONFIG_PATH
python3 modules/listen.py all --config agents/boty/config.json
python3 modules/gmail_poll.py --config agents/boty/config.json --summary
python3 modules/chat_poll.py --config agents/boty/config.json

# Heartbeat
AGENT_CONFIG_PATH=agents/boty/config.json node modules/heartbeat.js
```

## Ajouter un agent

```bash
cp -r agents/boty agents/eline
# Editer agents/eline/config.json (agent_id, gws_config_dir, senders...)
python3 modules/listen.py all --config agents/eline/config.json
```

## State files

Fichiers dans `/home/node/.config/gws/accounts/state/`:
- `{agent_id}-gmail.json` — IDs Gmail traites
- `{agent_id}-chat.json` — IDs Chat traites
