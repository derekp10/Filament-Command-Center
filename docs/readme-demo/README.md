# The README demo

An FCC with its own Spoolman and made-up spools and places, for the pictures in the repo's README (`docs/images/readme/`). It answers on this PC only: FCC at http://127.0.0.1:8100, its Spoolman at http://127.0.0.1:7999, and a fake PrusaLink for two printers (one printing, one idle). Nothing here reads or writes dev's or prod's data.

It is kept, stopped, between uses, so the next documentation update doesn't have to build another one (Derek, 2026-11-11). Its spools live in a Docker volume (`fcc-readme-demo_spoolman-data`), and its places in its own `app/data/` (git-ignored).

Run each command from the repo root in Git Bash. `py` below stands for `"C:/Python314/python.exe"`, the interpreter the tests use, which has Playwright and requests.

## Use it

1. `py docs/readme-demo/refresh_app.py`: copies the current code into the demo. Its made-up places stay.
2. `docker compose -f docs/readme-demo/docker-compose.yml -p fcc-readme-demo up -d`, then wait until http://127.0.0.1:8100 answers.
3. `py docs/readme-demo/readme_shots.py <a scratch folder>`: the five pictures. Copy only the ones that should change into `docs/images/readme/`, look at each, and set the README caption's date.
4. `docker compose -f docs/readme-demo/docker-compose.yml -p fcc-readme-demo stop`

After a code change while it runs: step 1, then `docker restart fcc_readme_demo`.

## Build it from nothing

When `docker ps -a` lists no `fcc_readme_demo` (a new PC, or after `down -v`):

1. `py docs/readme-demo/refresh_app.py`: the code, and the made-up places from `locations.seed.json`.
2. `docker compose -f docs/readme-demo/docker-compose.yml -p fcc-readme-demo up -d`, then wait until http://127.0.0.1:8100 answers.
3. `MSYS_NO_PATHCONV=1 docker exec fcc_readme_demo python /setup-and-rebuild/setup_fields.py`: Spoolman's extra fields. (Without `MSYS_NO_PATHCONV=1`, Git Bash turns the container's path into a Windows one, and Python can't find the file.)
4. `py docs/readme-demo/seed.py`: the made-up brands, filaments and spools (it refuses to seed a Spoolman that has spools).
5. Then "Use it", step 3.

## Rules

- Made-up data only. Never copy dev's or prod's places or spools in: `refresh_app.py` copies only the code git tracks, never `inventory-hub/data/`.
- No picture of ⚙️ Settings: on a real FCC it shows printer API keys (the demo's are fake).
- Its scripts refuse any address but the demo's (7999, 8100), and those two ports must be free to start it.
- Remove it with `docker compose -f docs/readme-demo/docker-compose.yml -p fcc-readme-demo down -v`, never with `--rmi`: it runs dev's own image, `inventory-hub-inventory-hub`.

## What is here

- `docker-compose.yml`: the three containers. `config.json`: FCC's settings for the demo. `fakelink/fakelink.py`: the fake PrusaLink.
- `locations.seed.json`: the made-up places: rooms WORKSHOP and OFFICE, SHELF-1 and SHELF-2, BIN-1, DRYBOX-1 (4 slots, feeding PRINTER-1's heads), the single dryer DRYBOX-2, PRINTER-1 with HEAD-1 to HEAD-4, and PRINTER-2 with HEAD-5. The printers' logins are fake.
- `seed.py`, `refresh_app.py`, `readme_shots.py`: above. The dashboard picture shows two spools moved and two left in the buffer; when the buffer is empty (it empties when the demo's FCC restarts), `readme_shots.py` makes that state with six typed scans.
- Git-ignored: `app/` (the code copy and the demo's own data), `setup-and-rebuild/` (a copy of `setup_fields.py`) and `labels/` (the label CSVs the demo writes).
