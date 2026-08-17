"""Configuration for the content processing pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class ProcessorSettings:
    raw_dir: Path = ROOT_DIR / "data" / "raw"
    output_dir: Path = ROOT_DIR / "data" / "processed"
    chunk_size_tokens: int = 1000
    chunk_overlap_tokens: int = 150
    min_chunk_tokens: int = 40
    source_type: str = "bmi_hub_page"

    @classmethod
    def from_env(cls) -> ProcessorSettings:
        return cls(
            raw_dir=Path(os.getenv("PROCESSOR_RAW_DIR", str(ROOT_DIR / "data" / "raw"))),
            output_dir=Path(
                os.getenv("PROCESSOR_OUTPUT_DIR", str(ROOT_DIR / "data" / "processed"))
            ),
            chunk_size_tokens=int(os.getenv("PROCESSOR_CHUNK_SIZE_TOKENS", "1000")),
            chunk_overlap_tokens=int(os.getenv("PROCESSOR_CHUNK_OVERLAP_TOKENS", "150")),
            min_chunk_tokens=int(os.getenv("PROCESSOR_MIN_CHUNK_TOKENS", "40")),
            source_type=os.getenv("PROCESSOR_SOURCE_TYPE", "bmi_hub_page"),
        )
