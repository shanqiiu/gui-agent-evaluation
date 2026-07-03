from importlib import import_module

from .config import Config

__all__ = ["Config", "sequence", "single_step"]


def __getattr__(name):
    if name in {"sequence", "single_step"}:
        module = import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")