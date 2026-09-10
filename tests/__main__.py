import sys
import warnings
from pathlib import Path

# Safe stdout reconfigure for Windows codepages
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

print("🚀 Initializing Pipeline Tools Test Suite...\n", flush=True)

# Suppress warnings
warnings.filterwarnings("ignore", category=ResourceWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)

sys.path.insert(0, str(Path(__file__).parent.parent))

# Pre-flight embedded PostgreSQL lock self-healing
try:
    from src.db.manager import DBManager
    heal_res = DBManager.heal_postgres_locks()
    if heal_res.get("status") == "healed":
        print(f"🔧 Pre-flight: Self-healed embedded PostgreSQL locks ({len(heal_res.get('orphaned_pids_killed', []))} orphaned processes, {len(heal_res.get('stale_pids_removed', []))} stale PIDs removed).\n", flush=True)
except Exception:
    pass

from tests.test_app import run_tests

if __name__ == '__main__':
    success = run_tests()
    sys.exit(not success)

