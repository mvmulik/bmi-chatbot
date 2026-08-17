"""Allow `python -m processor` from the project root."""

from processor.pipeline import main

if __name__ == "__main__":
    raise SystemExit(main())
