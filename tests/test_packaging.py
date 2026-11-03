import importlib

import pytest


@pytest.mark.parametrize("module", ["collector", "spark_jobs", "quality"])
def test_first_party_packages_are_importable(module: str) -> None:
    importlib.import_module(module)
