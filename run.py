# run.py
import webbrowser

import uvicorn

from revelado.config import SETTINGS

if __name__ == "__main__":
    webbrowser.open(f"http://localhost:{SETTINGS.port}")
    uvicorn.run("revelado.server:app", host="127.0.0.1", port=SETTINGS.port)
