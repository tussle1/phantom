"""Bounded process IPC. The control panel never runs RPM/input on its UI thread."""
from __future__ import annotations

import multiprocessing as mp
import queue
import sys
import time

from .schema import load_profile
from .config import validate_config


def worker(profile_path, document, path, commands, events, stop, pause):
    def report(event):
        try:
            events.put_nowait(event)
        except queue.Full:
            pass
    failed = False
    try:
        from phantom import run
        profile = load_profile(profile_path)
        config = validate_config(document)
        run(profile, config, path, control=commands, stop_event=stop, report=report, pause_event=pause)
    except Exception as error:
        failed = True
        report({'kind': 'error', 'message': str(error)})
    finally:
        report({'kind': 'stopped'})
        # The GUI drains while stopping; flush the final error before the process exits.
        # Its 3-second stop watchdog remains the upper bound if the reader disappears.
        events.close()
        events.join_thread()
    if failed:
        raise SystemExit(1)


class RuntimeSession:
    def __init__(self):
        self.context = mp.get_context('spawn')
        self.process = None
        self.commands = self.events = self.stop_event = None
        self.pending = None
        self.stopping_since = None
        self.pause_event = None
        self.menu_visible = True

    @property
    def running(self):
        return self.process is not None and self.process.is_alive()

    def start(self, profile_path, document, path):
        if self.process is not None:
            raise ValueError('Stop the existing runtime before starting another.')
        if sys.platform != 'win32':
            raise OSError('The native runtime requires Windows. The panel itself can be previewed here.')
        load_profile(profile_path)
        validate_config(document)
        self.commands = self.context.Queue(maxsize=4)
        self.events = self.context.Queue(maxsize=32)
        self.stop_event = self.context.Event()
        self.pause_event = self.context.Event()
        if self.menu_visible:
            self.pause_event.set()
        self.process = self.context.Process(target=worker,
            args=(profile_path, document, path, self.commands, self.events, self.stop_event, self.pause_event),
            name='Phantom native runtime', daemon=True)
        try:
            self.process.start()
        except Exception:
            self._dispose()
            raise
        self.stopping_since = None

    def update(self, settings, revision):
        validate_config({'version': 1, 'settings': settings})
        if type(revision) is not int or revision < 0:
            raise ValueError('Invalid settings revision.')
        if self.running:
            # Coalesce UI changes when the child is busy, rather than blocking Qt.
            self.pending = {'kind': 'config', 'settings': settings, 'revision': revision}
            self.flush()

    def flush(self):
        if self.pending is not None and self.running:
            try:
                self.commands.put_nowait(self.pending)
                self.pending = None
            except queue.Full:
                pass

    def set_menu_visible(self, visible):
        self.menu_visible = bool(visible)
        if self.pause_event is not None:
            (self.pause_event.set if self.menu_visible else self.pause_event.clear)()

    def stop(self):
        if self.running and self.stopping_since is None:
            self.stopping_since = time.monotonic()
            self.stop_event.set()

    def poll(self):
        result = []
        if self.events is not None:
            for _ in range(64):
                try:
                    result.append(self.events.get_nowait())
                except queue.Empty:
                    break
        if self.process is not None:
            if self.running and self.stopping_since is not None and time.monotonic()-self.stopping_since > 3:
                self.process.terminate()
                result.append({'kind': 'error', 'message': 'Runtime did not stop in time; its process was terminated.'})
            if not self.running:
                code = self.process.exitcode
                self.process.join(timeout=0)
                self._dispose()
                if code not in (None, 0) and not any(event.get('kind') == 'error' for event in result):
                    result.append({'kind': 'error', 'message': f'Runtime exited with code {code}.'})
                result.append({'kind': 'stopped'})
        self.flush()
        return result

    def _dispose(self):
        for pipe in (self.commands, self.events):
            if pipe is not None:
                pipe.cancel_join_thread()
                pipe.close()
        if self.process is not None and self.process.pid is not None:
            self.process.close()
        self.process = self.commands = self.events = self.stop_event = self.pause_event = None
        self.pending = None
        self.stopping_since = None
