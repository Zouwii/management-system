"""Knowledge module — document browsing and downloading from DingTalk knowledge base."""

from ai.knowledge.routes import register as _register_routes


def register(bp, ok, fail):
    """Register knowledge base HTTP routes on the given Flask Blueprint."""
    _register_routes(bp, ok, fail)
