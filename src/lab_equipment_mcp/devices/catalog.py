from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .agilent.dsox2012a import DSOX2012A_PROFILE
from .agilent.series_33500b import AGILENT_33500B_PROFILE
from .gw_instek.afg_2125 import AFG2125_PROFILE
from .siglent.sdg_1000x import SIGLENT_SDG1000X_PROFILE
from .tektronix.dpo2012b import DPO2012B_PROFILE

DEVICE_PROFILES = (
    DPO2012B_PROFILE,
    AFG2125_PROFILE,
    AGILENT_33500B_PROFILE,
    SIGLENT_SDG1000X_PROFILE,
    DSOX2012A_PROFILE,
)


def list_device_profiles() -> list[dict[str, Any]]:
    return [asdict(profile) for profile in DEVICE_PROFILES]
