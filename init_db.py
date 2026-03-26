"""
Backward-compatible wrapper for database initialization.
"""

import asyncio

from manage_db import init_database


if __name__ == "__main__":
    asyncio.run(init_database())
