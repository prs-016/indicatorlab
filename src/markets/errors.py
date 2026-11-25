"""Shared lookup errors; the team resolver can re-export these exact classes."""


class UnknownTicker(ValueError):
    """A malformed symbol or a provider-confirmed absence of price history."""


class SymbolLookupUnavailable(RuntimeError):
    """The history provider could not confirm a symbol because its service failed."""
