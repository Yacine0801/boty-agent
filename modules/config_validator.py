"""
config_validator.py — Validates agent config at boot.
"""
import logging

logger = logging.getLogger("agent")

def validate_config(config: dict, required_fields: list) -> None:
    missing = [f for f in required_fields if not config.get(f)]
    for field in missing:
        logger.error(f"AGENT CONFIG ERROR: champ requis manquant: {field}")
    if missing:
        raise SystemExit("Config invalide — agent refusé au boot")
