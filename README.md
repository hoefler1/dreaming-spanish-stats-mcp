ds_mcp_server.py — Dreaming Spanish als MCP-Server.

Stellt deine Dreaming-Spanish-Fortschrittsdaten als MCP-Tools bereit, sodass ein
MCP-Client (z. B. Claude Desktop) Fragen wie „Wie ist mein DS-Fortschritt?" oder
„Wann erreiche ich 300 Stunden?" beantworten kann.

Eigenständig — hängt nur am offiziellen MCP-SDK ab.

INSTALLATION
------------
    pip install "mcp[cli]"          # oder: uv add "mcp[cli]"

TOKEN
-----
Der Bearer-Token wird aus der Umgebungsvariable DS_TOKEN gelesen und NICHT im
Code gespeichert. So findest du ihn:
app.dreaming.com einloggen -> F12 -> Network -> Seite neu laden ->
Anfrage an ".netlify/functions/..." -> Request Header
"Authorization: Bearer XXXX" -> nur den Teil nach "Bearer " kopieren.

LOKAL TESTEN
------------
    export DS_TOKEN="dein_token"     # Windows PowerShell: $env:DS_TOKEN="..."
    python ds_mcp_server.py          # startet den stdio-Server

EINBINDUNG IN CLAUDE DESKTOP
----------------------------
In claude_desktop_config.json (Windows:
%APPDATA%\\Claude\\claude_desktop_config.json):

    {
      "mcpServers": {
        "dreaming-spanish": {
          "command": "python",
          "args": ["C:\\\\Pfad\\\\zu\\\\ds_mcp_server.py"],
          "env": { "DS_TOKEN": "dein_token_hier" }
        }
      }
    }

Hinweis: inoffizieller interner DS-Endpunkt; er kann sich jederzeit ändern.