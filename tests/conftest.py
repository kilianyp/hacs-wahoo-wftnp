"""Test configuration for the Wahoo WFTNP integration."""

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations,
):
    """Enable all integration in tests"""
    yield
