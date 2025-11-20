"""
Progress tracking utilities for long-running operations.
Copyright (c) 2025 Oracle and/or its affiliates.
"""

import sys
import time
import threading
from itertools import cycle


class ProgressSpinner:
    """Simple progress spinner for long-running operations."""
    
    def __init__(self, message="Processing"):
        self.message = message
        self.spinner_chars = cycle(['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'])
        self.stop_event = threading.Event()
        self.thread = None
        self.start_time = None
    
    def _format_time(self, seconds):
        """Format seconds to human readable format."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins}m {secs}s"
        else:
            hours = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            return f"{hours}h {mins}m"
    
    def _spinner_animation(self):
        """Display spinning animation with elapsed time."""
        while not self.stop_event.is_set():
            char = next(self.spinner_chars)
            elapsed = time.time() - self.start_time
            elapsed_str = self._format_time(elapsed)
            sys.stdout.write(f"\r{char} {self.message} ({elapsed_str} elapsed)")
            sys.stdout.flush()
            time.sleep(0.1)
        sys.stdout.write("\r")
        sys.stdout.flush()
    
    def start(self):
        """Start the spinner."""
        self.start_time = time.time()
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._spinner_animation, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Stop the spinner."""
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=1)


class ProgressTracker:
    """Track progress with ETA calculation."""
    
    def __init__(self, total_items, operation_name="Processing"):
        self.total_items = total_items
        self.operation_name = operation_name
        self.completed_items = 0
        self.start_time = time.time()
    
    def _format_time(self, seconds):
        """Format seconds to human readable format."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins}m {secs}s"
        else:
            hours = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            return f"{hours}h {mins}m"
    
    def update(self, current_item):
        """Update progress and display with ETA."""
        self.completed_items = current_item
        elapsed = time.time() - self.start_time
        
        if current_item > 0:
            rate = elapsed / current_item  # seconds per item
            remaining_items = self.total_items - current_item
            eta_seconds = rate * remaining_items
            eta_str = self._format_time(eta_seconds)
        else:
            eta_str = "calculating..."
        
        elapsed_str = self._format_time(elapsed)
        percentage = (current_item / self.total_items * 100) if self.total_items > 0 else 0
        
        # Create progress bar
        bar_length = 30
        filled = int(bar_length * current_item / self.total_items) if self.total_items > 0 else 0
        bar = '█' * filled + '░' * (bar_length - filled)
        
        sys.stdout.write(
            f"\r  [{bar}] {percentage:.1f}% | "
            f"{current_item}/{self.total_items} | "
            f"⏱️  {elapsed_str} | "
            f"⏳ ETA: {eta_str}"
        )
        sys.stdout.flush()
    
    def finish(self):
        """Display final progress."""
        elapsed = time.time() - self.start_time
        elapsed_str = self._format_time(elapsed)
        sys.stdout.write(f"\r✅ Completed {self.completed_items}/{self.total_items} in {elapsed_str}\n")
        sys.stdout.flush()
