"""Parametric 3D-printable enclosures for PCBs, built with build123d."""

from .config import ConfigError, Params, load, params_from_dict
from .geometry import Enclosure, build

__all__ = ["ConfigError", "Enclosure", "Params", "build", "load", "params_from_dict"]
__version__ = "0.1.0"
