from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .tektronix.dpo2012b import DPO2012B_PROFILE

DEVICE_PROFILES = (DPO2012B_PROFILE,)


def list_device_profiles() -> list[dict[str, Any]]:
    return [asdict(profile) for profile in DEVICE_PROFILES]

