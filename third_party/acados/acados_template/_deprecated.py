from __future__ import annotations

import functools
import warnings
from collections.abc import Callable


def deprecated(*, version: str | None = None, reason: str | None = None) -> Callable:
  details = "This API is deprecated."
  if version and reason:
    details = f"This API is deprecated since {version}: {reason}"
  elif version:
    details = f"This API is deprecated since {version}."
  elif reason:
    details = f"This API is deprecated: {reason}"

  def decorate(fn: Callable) -> Callable:
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
      warnings.warn(details, DeprecationWarning, stacklevel=2)
      return fn(*args, **kwargs)

    return wrapped

  return decorate
