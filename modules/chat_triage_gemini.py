"""
chat_triage_gemini.py — Chat polling + triage via Gemini 2.5 Flash.
Auto-discovers all spaces. No Claude container needed.

Usage:
  python3 chat_triage_gemini.py --config agents/boty/config.json
  python3 chat_triage_gemini.py --config agents/thais/config.json --dry-run
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_config import load_config, get_config
from state import get_processed_ids, add_processed_ids, set_last_check
from triage_gemini import call_gemini, write_ipc, track_gemini_cost

CHANNEL = "chat"


def run_gws(args: list, config_dir: str) -> dict:
    env = os.environ.copy()
    env["GOOGLE_WORKSPACE_CLI_CONFIG_DIR"] = config_dir
    r = subprocess.run(["gws"] + args, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return json.loads(r.stdout)


def list_spaces(config_dir: str) -> list:
    try:
        data = run_gws(["chat", "spaces", "list", "--params",
                        json.dumps({"pageSize": 100})], config_dir)
        return [s for s in data.get("spaces", [])
                if s.get("type") in ("ROOM", "SPACE", "GROUP_CHAT")]
    except RuntimeError:
        return []


def fetch_messages(space_id: str, config_dir: str, page_size: int = 15) -> list:
    data = run_gws(["chat", "spaces", "messages", "list", "--params",
                    json.dumps({"parent": space_id, "pageSize": page_size,
                                "orderBy": "createTime desc"})], config_dir)
    return data.get("messages", [])


def send_reply(space_id: str, text: str, config_dir: str):
    env = os.environ.copy()
    env["GOOGLE_WORKSPACE_CLI_CONFIG_DIR"] = config_dir
    subprocess.run(["gws", "chat", "+send", "--space", space_id, "--text", text],
                   capture_output=True, text=True, env=env)


CHAT_SYSTEM = """You are a chat message triage assistant. For each new message, decide:

- IGNORE: bot messages, automated notifications, messages not directed at the agent, or messages that don't need a response.
- RESPOND: messages from team members that expect a reply. Provide the reply text. Keep replies concise and professional.
- ESCALATE: complex questions requiring strategic analysis, code review, or sensitive decisions.

Return a JSON array. Each element:
{"id": "msg_id", "action": "IGNORE|RESPOND|ESCALATE", "summary": "1 line", "reply": "only if RESPOND"}

All chat is internal — no external_comms restrictions apply here."""


def classify_messages(messages: list, agent_context: str) -> list:
    if not messages:
        return []

    msg_text = "\n\n".join([
        f"[ID: {m['id']}] [Space: {m.get('space_name','')}]\n"
        f"Sender: {m.get('sender_name', 'unknown')}\n"
        f"Text: {m.get('text', '')}"
        for m in messages
    ])

    prompt = f"Agent context:\n{agent_context}\n\nMessages to classify:\n\n{msg_text}"

    raw = call_gemini(prompt, system=CHAT_SYSTEM)
    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(clean)
    except json.JSONDecodeError:
        return [{"id": m["id"], "action": "IGNORE", "summary": ""} for m in messages]


def poll(config_path: str = None, dry_run: bool = False):
    cfg = get_config() if config_path is None else load_config(config_path)
    agent_id = cfg["agent_id"]
    config_dir = cfg["gws_config_dir"]

    spaces = list_spaces(config_dir)
    if not spaces:
        return {"agent_id": agent_id, "spaces": 0, "new": 0}

    processed = get_processed_ids(agent_id, channel=CHANNEL)
    all_new = []

    for space in spaces:
        space_id = space.get("name", "")
        space_name = space.get("displayName", space_id)
        if not space_id:
            continue

        try:
            messages = fetch_messages(space_id, config_dir)
        except RuntimeError as e:
            print(f"[chat_triage] Error polling {space_name}: {e}", file=sys.stderr)
            continue

        for m in messages:
            mid = m.get("name", "").split("/")[-1]
            if not mid or mid in processed:
                continue
            if m.get("sender", {}).get("type") == "BOT":
                processed.add(mid)
                continue

            all_new.append({
                "id": mid,
                "space_id": space_id,
                "space_name": space_name,
                "sender_name": m.get("sender", {}).get("displayName", "unknown"),
                "text": m.get("text", m.get("argumentText", "")),
                "create_time": m.get("createTime", ""),
            })

    if not all_new:
        set_last_check(agent_id, channel=CHANNEL)
        return {"agent_id": agent_id, "spaces": len(spaces), "new": 0}

    # Classify via Gemini
    agent_context = f"Agent: {agent_id}"
    print(f"[chat_triage] Classifying {len(all_new)} messages across {len(spaces)} spaces...")
    classifications = classify_messages(all_new, agent_context)
    class_map = {c["id"]: c for c in classifications}

    actions = {"IGNORE": 0, "RESPOND": 0, "ESCALATE": 0}
    escalate_items = []

    for msg in all_new:
        c = class_map.get(msg["id"], {"action": "IGNORE"})
        action = c.get("action", "IGNORE")
        actions[action] = actions.get(action, 0) + 1

        if not dry_run:
            if action == "RESPOND" and c.get("reply"):
                send_reply(msg["space_id"], c["reply"], config_dir)
                print(f"[chat_triage] Replied in {msg['space_name']}: {c['reply'][:60]}...")
            elif action == "ESCALATE":
                escalate_items.append({**msg, **c})

    if not dry_run:
        all_ids = [m["id"] for m in all_new]
        add_processed_ids(agent_id, all_ids, channel=CHANNEL)
        set_last_check(agent_id, channel=CHANNEL)

        if escalate_items:
            ipc_dir = os.environ.get("IPC_DIR", "/tmp")
            write_ipc(agent_id, "ESCALATE", escalate_items, ipc_dir)

    result = {"agent_id": agent_id, "spaces": len(spaces), "new": len(all_new), "actions": actions}
    print(f"[chat_triage] Result: {json.dumps(result)}")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    if args.config:
        load_config(args.config)
    result = poll(dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
