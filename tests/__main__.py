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

from tests.test_app import run_tests

if __name__ == '__main__':
    success = run_tests()
    sys.exit(not success)
