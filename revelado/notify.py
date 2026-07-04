import subprocess


def notify_macos(title: str, message: str) -> None:
    try:
        script = f'display notification "{message}" with title "{title}" sound name "Glass"'
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
    except Exception:
        pass  # la notificación nunca debe romper el flujo
