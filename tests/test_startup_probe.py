"""Startup observations must preserve the executor's existing freshness window."""

import importlib.util

import pytest


@pytest.mark.parametrize(
    "age,expected",
    [
        (-0.20001, False),
        (-0.2, True),
        (0, True),
        (1, True),
        (1.00001, False),
        (None, False),
        (float("nan"), False),
    ],
)
def test_startup_probe_freshness(age, expected):
    spec = importlib.util.spec_from_file_location("startup", "scripts/probe_ros_startup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.fresh(1, age, 0) == expected
    assert module.fresh(1, 0, age) == expected
    assert not module.fresh(0, age, age)
