"""Central configuration. All tunables live here so experiments are reproducible."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
KB_DIR = DATA_DIR / "kb"
CASES_DIR = DATA_DIR / "cases"
CACHE_DIR = ROOT / ".cache"
RESULTS_DIR = ROOT / "results"

# --- LLM provider (OpenAI-compatible endpoint) ---
API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# Model roles. Keeping them separate lets us swap the agent model
# without changing the simulated user or the judge.
AGENT_MODEL = os.getenv("AGENT_MODEL", "deepseek-v4-pro")
USER_SIM_MODEL = os.getenv("USER_SIM_MODEL", "deepseek-flash")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "deepseek-flash")

TEMPERATURE = 0.0          # deterministic as far as the provider allows
MAX_RETRIES = 4
USE_CACHE = True           # cache identical requests on disk (saves cost, aids reproducibility)

# --- Agent limits ---
MAX_STEPS = 15             # max tool calls / questions per session
