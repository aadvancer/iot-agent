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

# --- Knowledge-base vector database (ChromaDB, persisted locally) ---
VECTOR_DB_DIR = Path(os.getenv("VECTOR_DB_DIR", CACHE_DIR / "chroma"))
EMBEDDING_MODEL = os.getenv("KB_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDING_CACHE_DIR = CACHE_DIR / "models"
KB_COLLECTION = "support_kb"

# --- LLM provider (OpenAI-compatible endpoint) ---
API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# Model roles. Keeping them separate lets us swap the agent model
# without changing the simulated user or the judge.
AGENT_MODEL = os.getenv("AGENT_MODEL", "deepseek-v4-pro")
USER_SIM_MODEL = os.getenv("USER_SIM_MODEL", "deepseek-flash")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "deepseek-flash")
REASONING_MODEL = os.getenv("REASONING_MODEL", AGENT_MODEL)
OUTPUT_MODEL = os.getenv("OUTPUT_MODEL", AGENT_MODEL)

TEMPERATURE = 0.0          # deterministic as far as the provider allows
# DeepSeek thinking mode: "disabled" (fast, ~5 s per agent step), "low"/"high"/"max"
# (chain-of-thought first; "high" took 1-3 min per step), or "default" to send nothing
# (use "default" for OpenAI-compatible providers that reject the parameter).
LLM_THINKING = os.getenv("LLM_THINKING", "disabled").strip().lower()
MAX_RETRIES = 4
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "120"))   # seconds per request
MAX_TIMEOUT_RETRIES = 1    # timed-out requests are retried at most this many times
USE_CACHE = True           # cache identical requests on disk (saves cost, aids reproducibility)
# Separate cache namespace for repeated runs (eval.run_cases --run N sets "run<N>"), so a
# repeat gets fresh model responses that are then cached for reproducible re-runs.
CACHE_NAMESPACE = os.getenv("LLM_CACHE_NAMESPACE", "")

# --- Agent limits ---
MAX_STEPS = 15             # max tool calls / questions per session
