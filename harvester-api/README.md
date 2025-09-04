# harvester-api
This directory contains the web API in `server.py`, which is a thin wrapper around the backend postgreSQL database.
The service also fetches app details from Google's and Apple's stores and links them to the corresponding database entry.

Additionally, it contains some tools and their dependencies to manage persona entries:
- `./persona_builder.py`: Used to create persona entries (see `./persona_builder.py -h` for further information).
- `./persona_transfer.py`: Helper script to transfer a persona from iOS to Android.
- `./google_persona_checker.py`: Helper script to check that the names associated with a persona have not changed since its creation.

## Setup
Create venv with requirements from `requirements.txt`.

## Usage
To run the REST API and detail fetching service, do the following:
```bash
waitress-serve --host 127.0.0.1 --port 5000 server:app
```
