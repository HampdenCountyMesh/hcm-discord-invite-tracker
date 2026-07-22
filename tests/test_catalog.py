from pathlib import Path

import pytest

from hcm_invite_tracker.catalog import SourceCatalog, validate_slug


def test_hcm_catalog_loads():
    path = Path(__file__).parents[1] / "config" / "hcm-sources.yml"
    catalog = SourceCatalog.load(path)
    assert catalog.project_name == "Hampden County Mesh"
    assert catalog.by_slug("better-coverage") is not None
    assert catalog.by_slug("general").preferred_invite_code == "egyUeREcmX"


def test_slug_validation():
    validate_slug("home-bottom")
    with pytest.raises(ValueError):
        validate_slug("Home Bottom")
