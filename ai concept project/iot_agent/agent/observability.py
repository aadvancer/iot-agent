"""Local rotating event logs without storing prompts or customer responses."""
import json
import logging
from logging.handlers import RotatingFileHandler

import config


class EventFormatter(logging.Formatter):
    def format(self, record):
        fields = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "event": getattr(record, "event", record.getMessage()),
        }
        for key in ("case_id", "step", "tool", "status", "detail"):
            value = getattr(record, key, None)
            if value is not None:
                fields[key] = value
        return json.dumps(fields, ensure_ascii=False)


def get_logger():
    logger = logging.getLogger("iot_agent")
    if not logger.handlers:
        config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            config.CACHE_DIR / "agent.log",
            maxBytes=5_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(EventFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
