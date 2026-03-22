"""
listen.py — Orchestrateur Mode Ecoute. Combine Gmail + Chat polling.
Usage : python3 listen.py [gmail|chat|all] --account yacine
"""
import argparse, json, os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gmail_poll, chat_poll

SPACES = {"sam":"spaces/AAQAF8zXzRE","yacine":"spaces/AAQAF8zXzRE"}

def listen(account="yacine", channels=None, space_id=None, dry_run=False):
    channels = channels or ["gmail","chat"]
    results = {"account":account,"timestamp":datetime.now(timezone.utc).isoformat(),"channels":{}}
    if "gmail" in channels:
        try:
            emails = gmail_poll.poll(account=account, dry_run=dry_run)
            results["channels"]["gmail"] = {"status":"ok","new_count":len(emails),"items":emails,
                                             "summary":gmail_poll.format_summary(emails)}
        except Exception as e:
            results["channels"]["gmail"] = {"status":"error","error":str(e)}
    if "chat" in channels:
        sid = space_id or SPACES.get(account, chat_poll.DEFAULT_SPACE)
        try:
            msgs = chat_poll.poll(account=account, space_id=sid, dry_run=dry_run)
            results["channels"]["chat"] = {"status":"ok","new_count":len(msgs),"items":msgs}
        except Exception as e:
            results["channels"]["chat"] = {"status":"error","error":str(e)}
    total = sum(r.get("new_count",0) for r in results["channels"].values() if isinstance(r,dict))
    results["total_new"] = total
    results["has_new"] = total > 0
    return results

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("channel", nargs="?", default="all", choices=["gmail","chat","all"])
    p.add_argument("--account", default="yacine")
    p.add_argument("--space-id", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    channels = ["gmail","chat"] if args.channel=="all" else [args.channel]
    result = listen(args.account, channels, args.space_id, args.dry_run)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n[Mode Ecoute] {result['account']} — {result['timestamp']}")
        print(f"Nouveaux : {result['total_new']}")
        for ch, d in result["channels"].items():
            if isinstance(d,dict):
                print(f"  {ch}: {d.get('status')} — {d.get('new_count',0)} nouveau(x)")
                if d.get("summary"): print(f"\n{d['summary']}")
                if d.get("error"): print(f"  ERREUR: {d['error']}")
