"""Allow `python -m crawler` from the project root."""

from crawler.crawler import main

if __name__ == "__main__":
    raise SystemExit(main())
