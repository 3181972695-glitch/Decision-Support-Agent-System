"""Global pytest configuration for the test suite."""

from __future__ import annotations


# Enable async test collection for all tests.
# Each async test still needs @pytest.mark.asyncio.
pytest_plugins = ("pytest_asyncio",)
