"""Typed errors for the YouTrack REST adapter."""

from __future__ import annotations


class YouTrackError(RuntimeError):
    """Raised for any non-success YouTrack REST response or shape violation."""
