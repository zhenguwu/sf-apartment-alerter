from __future__ import annotations

from ..config import SiteCfg
from .base import Site


def make_site(cfg: SiteCfg) -> Site:
    if cfg.type == "rentnema":
        from .rentnema import RentNema
        return RentNema(cfg)
    if cfg.type == "rentjasper":
        from .rentjasper import RentJasper
        return RentJasper(cfg)
    if cfg.type == "modera-rincon-hill":
        from .modera_rincon_hill import ModeraRinconHill
        return ModeraRinconHill(cfg)
    if cfg.type == "zillow":
        from .zillow import Zillow
        return Zillow(cfg)
    raise ValueError(
        f"Unknown site type: {cfg.type}. "
        f"Add a module in apt_scraper/sites/{cfg.type}.py and register it here."
    )


__all__ = ["Site", "make_site"]
