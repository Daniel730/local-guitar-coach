"""Pytest configuration: path setup + --hardware gate."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))


def pytest_addoption(parser):
    parser.addoption(
        "--hardware",
        action="store_true",
        default=False,
        help="run hardware smoke tests that need the M-Track Duo",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--hardware"):
        return
    skip = pytest.mark.skip(reason="pass --hardware to run audio-interface tests")
    for item in items:
        if "hardware" in item.keywords:
            item.add_marker(skip)
