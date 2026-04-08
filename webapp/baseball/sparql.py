"""Compatibility facade for SPARQL helpers.

Query implementations now live in the ``sparql_queries`` package split by domain.
Keep importing from ``baseball.sparql`` until the rest of the app is updated.
"""

from .sparql_queries import *  # noqa: F401,F403
