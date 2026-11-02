import sys
from pathlib import Path
import uvicorn

# Ensure the project root is in sys.path so 'app' can be found
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if __name__ == "__main__":
    print("Starting RegGuard AI FastAPI & SSE Server on http://localhost:8000 ...")
    uvicorn.run("app.server:app", host="0.0.0.0", port=8000, log_level="info", app_dir=str(PROJECT_ROOT))

