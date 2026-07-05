import threading
import webbrowser

import uvicorn

from revelado.config import SETTINGS

if __name__ == "__main__":
    # Abrir el navegador cuando el servidor ya esté arrancando
    threading.Timer(1.5, webbrowser.open,
                    args=(f"http://localhost:{SETTINGS.port}",)).start()
    uvicorn.run("revelado.server:app", host="127.0.0.1", port=SETTINGS.port)
