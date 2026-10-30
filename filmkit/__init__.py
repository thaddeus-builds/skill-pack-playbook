"""filmkit: a film spec in, a finished vertical (or any) film out. See docs/filmkit.md."""
__version__ = "0.1.2"

from .render import inspect, render, still  # noqa: F401
from .spec import SCHEMA, load, problems, require  # noqa: F401
from .util import FilmkitError  # noqa: F401
