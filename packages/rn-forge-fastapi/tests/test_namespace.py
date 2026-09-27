"""The `rn_forge.fastapi` / `fastapi` namespace collision, asserted rather than trusted."""

import fastapi
import pytest
from assertpy import assert_that

import rn_forge.fastapi

pytestmark = pytest.mark.unit


def test_the_package_and_the_framework_resolve_to_disjoint_paths():
    assert_that(set(rn_forge.fastapi.__path__) & set(fastapi.__path__)).is_empty()


def test_the_framework_is_the_real_framework():
    assert_that(fastapi.FastAPI.__module__).is_equal_to("fastapi.applications")


def test_every_public_name_resolves():
    for name in rn_forge.fastapi.__all__:
        assert_that(hasattr(rn_forge.fastapi, name)).described_as(name).is_true()
