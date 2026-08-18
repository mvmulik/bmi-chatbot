"""BMI Hub crawler package.

Note: this package intentionally avoids eagerly importing the ``crawler.crawler``
submodule here. Since that submodule shares its name with this package, an eager
``from crawler.crawler import ...`` at package-init time causes Python to see
``crawler.crawler`` partially bound in ``sys.modules`` before ``python -m
crawler.crawler`` finishes executing it as ``__main__``, which triggers a
RuntimeWarning and, in some invocation paths, an import failure. ``BmiHubCrawler``
and ``main`` are still available as ``crawler.BmiHubCrawler`` / ``crawler.main``
via lazy attribute access (PEP 562) without that hazard.
"""

from __future__ import annotations

from typing import Any

__all__ = ["BmiHubCrawler", "main"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from crawler.crawler import BmiHubCrawler, main

        return {"BmiHubCrawler": BmiHubCrawler, "main": main}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
