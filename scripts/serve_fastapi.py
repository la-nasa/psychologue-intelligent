#!/usr/bin/env python
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.fastapi_app import create_app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_app(), host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8000")), ws="websockets")  # nosec B104
