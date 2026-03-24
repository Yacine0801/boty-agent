"""
triage_gemini.py — Gmail triage via Gemini 2.5 Flash (Vertex AI).
No Claude container needed. Pure classification + routing.

Usage:
  python3 triage_gemini.py --config agents/boty/config.json
  python3 triage_gemini.py --config agents/thais/config.json --dry-run

external_comms config:
  mode: blocked | supervised | autonomous
  internal_domains: ["@bestoftours.co.uk", "@botler360.com"]
  whitelist: ["specific@external.com"]

  blocked    = internal chat/email OK, all external = DRAFT + NOTIFY
  supervised = internal OK, whitelisted external OK, rest = DRAFT + NOTIFY
  autonomous = all OK (future, for commercial agents)
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

SA_PATH = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "adp-service-account.json"),
)
# Fallback for container path
if not os.path.exists(SA_PATH):
    SA_PATH = "/workspace/project/adp-service-account.json"

PROJECT_ID = "adp-413110"
LOCATION = "us-central1"
MODEL = "gemini-2.5-flash"
CHANNEL = "gmail"

# ---------- Cost tracking ----------

COST_FILE = os.environ.get("GCP_COST_FILE", "/tmp/gemini-daily-spend.json")

def track_gemini_cost(input_chars: int, output_chars: int):
    """Track Gemini Flash costs. Approximate: $0.15/1M input chars, $0.60/1M output chars."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    spend = {"date": today, "input_chars": 0, "output_chars": 0, "estimated_usd": 0, "calls": 0}
    try:
        with open(COST_FILE) as f:
            data = json.load(f)
            if data.get("date") == today:
                spend = data
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    spend["input_chars"] += input_chars
    spend["output_chars"] += output_chars
    spend["calls"] += 1
    spend["estimated_usd"] = (spend["input_chars"] / 1_000_000) * 0.15 + (spend["output_chars"] / 1_000_000) * 0.60

    with open(COST_FILE, "w") as f:
        json.dump(spend, f, indent=2)


# ---------- Vertex AI Gemini call ----------

def call_gemini(prompt: str, system: str = "") -> str:
    """Call Gemini 2.5 Flash via Vertex AI REST API."""
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    import urllib.request

    creds = service_account.Credentials.from_service_account_file(
        SA_PATH, scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())

    url = (
        f"https://{LOCATION}-aiplatform.googleapis.com/v1/"
        f"projects/{PROJECT_ID}/locations/{LOCATION}/"
        f"publishers/google/models/{MODEL}:generateContent"
    )

    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 2048,
            "responseMimeType": "application/json",
        },
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    req_data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=req_data, headers={
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
    }, method="POST")

    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())

    text = result["candidates"][0]["content"]["parts"][0]["text"]
    track_gemini_cost(len(prompt) + len(system), len(text))
    return text


# ---------- GWS helpers ----------

def run_gws(args: list, config_dir: str) -> dict:
    env = os.environ.copy()
    env["GOOGLE_WORKSPACE_CLI_CONFIG_DIR"] = config_dir
    r = subprocess.run(["gws"] + args, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return json.loads(r.stdout)


def fetch_unread(config_dir: str, max_results: int = 10) -> list:
    data = run_gws([
        "gmail", "users", "messages", "list", "--params",
        json.dumps({"userId": "me", "q": "is:unread in:inbox", "maxResults": max_results}),
    ], config_dir)
    return data.get("messages", [])


def fetch_message(msg_id: str, config_dir: str) -> dict:
    data = run_gws([
        "gmail", "users", "messages", "get", "--params",
        json.dumps({"userId": "me", "id": msg_id, "format": "metadata",
                     "metadataHeaders": ["From", "Subject", "Date"]}),
    ], config_dir)
    headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
    return {
        "id": msg_id,
        "from": headers.get("From", ""),
        "subject": headers.get("Subject", ""),
        "date": headers.get("Date", ""),
        "snippet": data.get("snippet", ""),
    }


def mark_as_read(msg_id: str, config_dir: str):
    try:
        run_gws([
            "gmail", "users", "messages", "modify", "--params",
            json.dumps({"userId": "me", "id": msg_id}),
            "--json", json.dumps({"removeLabelIds": ["UNREAD"]}),
        ], config_dir)
    except Exception:
        pass


# ---------- External comms policy ----------

def extract_email(from_field: str) -> str:
    """Extract email from 'Name <email>' format."""
    if "<" in from_field and ">" in from_field:
        return from_field.split("<")[1].split(">")[0].lower()
    return from_field.strip().lower()


def is_internal(email: str, cfg: dict) -> bool:
    """Check if an email address is internal based on config."""
    ext_cfg = cfg.get("external_comms", {})
    internal_domains = ext_cfg.get("internal_domains", ["@bestoftours.co.uk"])
    return any(email.endswith(d) for d in internal_domains)


def is_whitelisted(email: str, cfg: dict) -> bool:
    """Check if external address is in the whitelist."""
    ext_cfg = cfg.get("external_comms", {})
    whitelist = ext_cfg.get("whitelist", [])
    return email in [w.lower() for w in whitelist]


def can_send_direct(sender_email: str, cfg: dict) -> bool:
    """Determine if agent can reply directly to this sender.
    Returns True for internal + whitelisted. False for blocked externals."""
    if is_internal(sender_email, cfg):
        return True

    mode = cfg.get("external_comms", {}).get("mode", "blocked")
    if mode == "autonomous":
        return True
    if mode == "supervised" and is_whitelisted(sender_email, cfg):
        return True
    return False


# ---------- Classification ----------

TRIAGE_SYSTEM = """You are an email triage assistant. Classify each email into exactly one action:

- IGNORE: newsletters, automated notifications, spam, noreply, marketing. Mark as read silently.
- NOTIFY: important emails the user should know about but that don't need a reply (FYI, confirmations, shipping notices).
- RESPOND: emails from team/contacts that expect a reply. Include a suggested_reply.
- ESCALATE: complex emails requiring strategic thinking, contract decisions, sensitive topics, or anything ambiguous.

Return a JSON array. Each element:
{"id": "msg_id", "action": "IGNORE|NOTIFY|RESPOND|ESCALATE", "urgency": "LOW|MEDIUM|HIGH", "summary": "1 line", "suggested_reply": "only if RESPOND"}

Be conservative: when in doubt, NOTIFY rather than IGNORE, ESCALATE rather than RESPOND."""


def classify_emails(emails: list, agent_context: str) -> list:
    if not emails:
        return []

    email_text = "\n\n".join([
        f"[ID: {e['id']}]\nFrom: {e['from']}\nSubject: {e['subject']}\nDate: {e['date']}\nSnippet: {e['snippet']}"
        for e in emails
    ])

    prompt = f"Agent context:\n{agent_context}\n\nEmails to classify:\n\n{email_text}"

    raw = call_gemini(prompt, system=TRIAGE_SYSTEM)
    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(clean)
    except json.JSONDecodeError:
        return [{"id": e["id"], "action": "NOTIFY", "urgency": "MEDIUM",
                 "summary": e["subject"]} for e in emails]


# ---------- Output / IPC ----------

def write_ipc(agent_id: str, action: str, items: list, ipc_dir: str = "/tmp"):
    if not items:
        return
    output = {
        "agent_id": agent_id,
        "action": action,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }
    outfile = os.path.join(ipc_dir, f"{agent_id}-triage-{action.lower()}.json")
    with open(outfile, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)


# ---------- Main ----------

def triage(config_path: str = None, dry_run: bool = False, max_results: int = 10):
    cfg = get_config() if config_path is None else load_config(config_path)
    agent_id = cfg["agent_id"]
    config_dir = cfg["gws_config_dir"]

    stubs = fetch_unread(config_dir, max_results)
    if not stubs:
        set_last_check(agent_id, channel=CHANNEL)
        return {"agent_id": agent_id, "new": 0, "actions": {}}

    processed = get_processed_ids(agent_id, channel=CHANNEL)
    new_stubs = [s for s in stubs if s["id"] not in processed]
    if not new_stubs:
        set_last_check(agent_id, channel=CHANNEL)
        return {"agent_id": agent_id, "new": 0, "actions": {}}

    emails = []
    for stub in new_stubs[:max_results]:
        try:
            emails.append(fetch_message(stub["id"], config_dir))
        except Exception as e:
            print(f"[triage] Failed to fetch {stub['id']}: {e}", file=sys.stderr)

    if not emails:
        return {"agent_id": agent_id, "new": 0, "actions": {}}

    # Build agent context
    agent_context = f"Agent: {agent_id}"
    urgent = cfg.get("gmail_urgent_senders", [])
    important = cfg.get("gmail_important_senders", [])
    if urgent:
        agent_context += f"\nUrgent senders: {', '.join(urgent)}"
    if important:
        agent_context += f"\nImportant senders: {', '.join(important)}"

    # Classify via Gemini
    print(f"[triage] Classifying {len(emails)} emails for {agent_id}...")
    classifications = classify_emails(emails, agent_context)
    class_map = {c["id"]: c for c in classifications}

    # Process with external_comms enforcement
    actions = {"IGNORE": [], "NOTIFY": [], "RESPOND": [], "RESPOND_DRAFT": [], "ESCALATE": []}
    for email in emails:
        c = class_map.get(email["id"], {"action": "NOTIFY", "urgency": "MEDIUM", "summary": email["subject"]})
        action = c.get("action", "NOTIFY")

        # Enforce external_comms policy on RESPOND
        if action == "RESPOND":
            sender_email = extract_email(email["from"])
            if can_send_direct(sender_email, cfg):
                actions["RESPOND"].append({**email, **c})
            else:
                # External sender, not whitelisted -> DRAFT + NOTIFY
                actions["RESPOND_DRAFT"].append({**email, **c, "reason": "external_blocked"})
        else:
            actions.setdefault(action, []).append({**email, **c})

    if not dry_run:
        all_ids = [e["id"] for e in emails]
        add_processed_ids(agent_id, all_ids, channel=CHANNEL)
        set_last_check(agent_id, channel=CHANNEL)

        for item in actions.get("IGNORE", []):
            mark_as_read(item["id"], config_dir)

        ipc_dir = os.environ.get("IPC_DIR", "/tmp")
        write_ipc(agent_id, "NOTIFY", actions.get("NOTIFY", []), ipc_dir)
        write_ipc(agent_id, "ESCALATE", actions.get("ESCALATE", []), ipc_dir)
        # RESPOND_DRAFT = blocked external replies → notify for human review
        if actions.get("RESPOND_DRAFT"):
            write_ipc(agent_id, "DRAFT", actions["RESPOND_DRAFT"], ipc_dir)

    result = {
        "agent_id": agent_id,
        "new": len(emails),
        "actions": {k: len(v) for k, v in actions.items() if v},
    }
    print(f"[triage] Result: {json.dumps(result)}")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max-results", type=int, default=10)
    args = p.parse_args()
    if args.config:
        load_config(args.config)
    result = triage(dry_run=args.dry_run, max_results=args.max_results)
    print(json.dumps(result, indent=2))
