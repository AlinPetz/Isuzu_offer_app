from contextlib import contextmanager
import os
import socket
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


HOST = "127.0.0.1"
PREFERRED_PORT = 8001
LOG_PATH = None


def _app_folder() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _prepare_stdio():
    global LOG_PATH
    LOG_PATH = _app_folder() / "ISUZU_Offer_App.log"
    if getattr(sys, "frozen", False) and (sys.stdout is None or sys.stderr is None):
        log_handle = LOG_PATH.open("a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = log_handle
        if sys.stderr is None:
            sys.stderr = log_handle


def _write_log(message: str):
    try:
        if LOG_PATH is None:
            return
        with LOG_PATH.open("a", encoding="utf-8") as log_file:
            log_file.write(message.rstrip() + "\n")
    except OSError:
        pass


_prepare_stdio()

try:
    import uvicorn

    from app.config import APP_NAME
    from app.main import app
except Exception:
    _write_log("Startup import failed:\n" + traceback.format_exc())
    raise


def main():
    _write_log("Starting ISUZU_Offer_App.")
    with _single_instance() as acquired:
        if not acquired:
            _write_log("This installation is already running; duplicate launch ignored.")
            return
        with _bind_listener() as listener:
            port = listener.getsockname()[1]
            url = f"http://{HOST}:{port}"
            server, thread = _start_server(listener)
            try:
                _wait_for_server(f"{url}/healthz", server)
                _show_application(url, server)
            finally:
                server.should_exit = True
                thread.join(timeout=8)
                _write_log("Server stopped." if not thread.is_alive() else "Server shutdown timed out.")


def _show_application(url, server):
    if getattr(sys, "frozen", False):
        _run_in_browser(url, server)
        return
    try:
        import webview
    except ImportError:
        _run_in_browser(url, server)
        return

    try:
        webview.create_window(
            APP_NAME,
            url,
            width=1240,
            height=860,
            min_size=(980, 700),
        )
        webview.start()
    except Exception:
        _write_log("Desktop window failed; falling back to browser:\n" + traceback.format_exc())
        _run_in_browser(url, server)
        return
    finally:
        server.should_exit = True


def _start_server(listener):
    config = uvicorn.Config(
        app,
        host=HOST,
        port=listener.getsockname()[1],
        loop="asyncio",
        http="h11",
        ws="none",
        lifespan="off",
        log_level="warning",
        access_log=False,
        log_config=None,
        use_colors=False,
        timeout_graceful_shutdown=5,
    )
    server = uvicorn.Server(config)
    server.launcher_errors = []

    def run_server():
        try:
            server.run(sockets=[listener])
        except (Exception, SystemExit):
            error = traceback.format_exc()
            server.launcher_errors.append(error)
            _write_log("Server thread failed:\n" + error)

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    return server, thread


def _wait_for_server(url: str, server: uvicorn.Server):
    deadline = time.time() + 12
    while time.time() < deadline:
        if getattr(server, "launcher_errors", []):
            raise RuntimeError(
                "Server failed during startup. "
                f"See log file: {LOG_PATH}"
            )
        try:
            with urllib.request.urlopen(url, timeout=0.5):
                _write_log(f"Server started at {url}")
                return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.15)
    raise RuntimeError(f"Server did not start at {url}. See log file: {LOG_PATH}")


def _bind_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == "nt":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind((HOST, PREFERRED_PORT))
        except OSError:
            sock.bind((HOST, 0))
            _write_log(f"Port {PREFERRED_PORT} unavailable; using {sock.getsockname()[1]}.")
        return sock
    except OSError:
        sock.close()
        raise


@contextmanager
def _single_instance():
    if os.name != "nt" or not getattr(sys, "frozen", False):
        yield True
        return
    import msvcrt

    with (_app_folder() / ".instance.lock").open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def _safe_print(message: str):
    try:
        print(message)
    except AttributeError:
        pass


def _run_in_browser(url: str, server: uvicorn.Server):
    opened = webbrowser.open(url)
    _write_log(f"Browser launch {'accepted' if opened else 'not accepted'}: {url}")
    _safe_print(f"{APP_NAME} is running at {url}")
    if getattr(sys, "frozen", False):
        try:
            _run_control_window(url, server)
            return
        except Exception:
            _write_log("Control window failed:\n" + traceback.format_exc())
            raise
    try:
        while not server.should_exit:
            time.sleep(0.5)
    except KeyboardInterrupt:
        server.should_exit = True


def _run_control_window(url: str, server: uvicorn.Server):
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title(APP_NAME)
    root.geometry("420x170")
    root.resizable(False, False)

    def stop_app():
        server.should_exit = True
        root.destroy()

    frame = ttk.Frame(root, padding=18)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="ISUZU_Offer_App ruleaza in browser.").pack(anchor="w")
    ttk.Label(frame, text="Inchide aceasta fereastra cand ai terminat.").pack(anchor="w", pady=(6, 16))

    actions = ttk.Frame(frame)
    actions.pack(fill="x")
    ttk.Button(actions, text="Deschide din nou", command=lambda: webbrowser.open(url)).pack(side="left")
    ttk.Button(actions, text="Opreste aplicatia", command=stop_app).pack(side="right")

    root.protocol("WM_DELETE_WINDOW", stop_app)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _write_log("Launcher failed:\n" + traceback.format_exc())
        raise
