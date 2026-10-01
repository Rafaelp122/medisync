"""Domain helper functions for the identity module."""

import re


def clean_digits(val: str) -> str:
    """Strip all non-numeric characters from a string."""
    return re.sub(r"\D", "", val)
