"""Точка входа для запуска: python -m checko_mcp"""

import asyncio

from .server import run


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
