"""
Real-time row-level progress tracking during Pixeltable computed column execution.
Provides dynamic ETA, throughput (rows/sec), and current item feedback for Gradio.
"""

import time
from pathlib import Path
from typing import Optional, Callable, Any


class RowProgressTracker:
    """
    Context-aware row-level progress tracker called directly inside Pixeltable @pxt.udf functions.
    Bridges backend row evaluation with Gradio's gr.Progress callback.
    """
    _callback: Optional[Callable[[float, str], None]] = None
    _operation_name: str = ""
    _total_rows: int = 0
    _processed_rows: int = 0
    _start_time: float = 0.0

    @classmethod
    def set_callback(cls, callback: Optional[Callable[[float, str], None]]) -> None:
        """Explicitly set global progress callback for upcoming operations."""
        cls._callback = callback

    @classmethod
    def start(
        cls,
        operation_name: str,
        total_rows: int,
        callback: Optional[Callable[[float, str], None]] = None
    ) -> None:
        """Initialize tracker for an upcoming table operation."""
        cls._operation_name = operation_name
        cls._total_rows = max(1, total_rows)
        cls._processed_rows = 0
        cls._start_time = time.time()
        if callback is not None:
            cls._callback = callback
        if cls._callback:
            try:
                cls._callback(0.0, f"⏳ {cls._operation_name}: Preparing 0/{cls._total_rows} rows...")
            except Exception:
                pass

    @classmethod
    def step(cls, row_label: str = "") -> None:
        """Invoked by @pxt.udf functions as each row is evaluated."""
        cls._processed_rows += 1
        if cls._callback:
            try:
                elapsed = max(0.001, time.time() - cls._start_time)
                rate = cls._processed_rows / elapsed
                remaining = max(0, cls._total_rows - cls._processed_rows)
                eta_sec = remaining / rate if rate > 0 else 0
                pct = min(1.0, cls._processed_rows / cls._total_rows)

                name_part = f"[{Path(row_label).name}] " if row_label else ""
                eta_str = f"{eta_sec:.0f}s" if eta_sec < 60 else f"{int(eta_sec // 60)}m {int(eta_sec % 60)}s"
                msg = (
                    f"⚡ {cls._operation_name}: Row {cls._processed_rows}/{cls._total_rows} "
                    f"{name_part}({rate:.1f} rows/s | ETA: {eta_str})"
                )
                cls._callback(pct, msg)
            except Exception:
                pass

    @classmethod
    def finish(cls, summary: str = "") -> None:
        """Complete tracking session and report final duration."""
        if cls._callback:
            try:
                elapsed = max(0.001, time.time() - cls._start_time)
                rate = cls._processed_rows / elapsed if elapsed > 0 else 0
                msg = summary or f"✅ {cls._operation_name}: Completed {cls._processed_rows} rows in {elapsed:.1f}s ({rate:.1f} rows/s)"
                cls._callback(1.0, msg)
            except Exception:
                pass
        cls._total_rows = 0
        cls._processed_rows = 0
        cls._start_time = 0.0
        cls._operation_name = ""

    @classmethod
    def reset(cls) -> None:
        """Reset internal state including callback."""
        cls._callback = None
        cls._total_rows = 0
        cls._processed_rows = 0
        cls._start_time = 0.0
        cls._operation_name = ""
