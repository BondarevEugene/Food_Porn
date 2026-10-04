"""
==========================================================
FOOD_PORN

Module: Process Entry Point
Layer: Entry Point

Responsibilities:
    - Start the asynchronous application
    - Handle normal operator shutdown signals
==========================================================
"""

import asyncio

from app.main import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
