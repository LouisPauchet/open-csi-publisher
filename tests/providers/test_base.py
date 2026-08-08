from __future__ import annotations

from open_csi_publisher.providers.base import empty_dataset


def test_empty_dataset_has_zero_length_time_coordinate():
    ds = empty_dataset()
    assert ds.sizes.get("time", 0) == 0
    assert "time" in ds.coords
