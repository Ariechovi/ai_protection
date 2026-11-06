import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="run tests that require the configured PostgreSQL, Redis and model APIs",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: requires real PostgreSQL, Redis and model APIs",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-integration"):
        return
    skip_integration = pytest.mark.skip(reason="use --run-integration to enable")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
