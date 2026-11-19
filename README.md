# Home Panel

Wall-mounted iPad dashboard for Home Assistant (lights, AC, scenes, Spotify with lyrics, weather, internet speed, batteries, interactive room view).

Served by Home Assistant from `config/www/panel/` at `http://homehub.local:8123/local/panel/index.html`.
The mini PC pulls this repository every few minutes, and open panels reload themselves when `version.json` changes.

Open `index.html` directly in a browser (or add `?demo`) to see it with demo data.
