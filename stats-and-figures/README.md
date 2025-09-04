# Statistics and Figures
This directory contains scripts to reproduce the figures and Table 1 within our paper.

## Usage instructions
To build and start the docker container serving the database, run:
```bash
cd database
docker network create app-store-network
docker build -t postgres-app-store .
docker run -d --name postgres-app-store -p 5432:5432 --network app-store-network postgres-app-store
```
### Figures
Now, you can run the `generate_plots.py` file to generate the figures from the paper.
If you have [uv](https://docs.astral.sh/uv/) installed, you can simply do:
```bash
./generate_plots.py
```

Otherwise, you need to manually install the dependencies outlined in the PEP 723 script tag before running this script:
```bash
python3 -m venv stats-and-figures/.venv
source stats-and-figures/.venv/bin/activate
pip install -r stats-and-figures/requirements.txt
./generate_plots.py
```

You should find all figures from our paper in `gen/` after running this script.

### Table 1
You can run the following docker container to recreate Table 1 of our paper.
This command takes approx. 1 hour to complete.
```sh
cd r_scripts
docker build -t r-chi-square .
cd ..
docker run -v ./gen:/usr/local/src/gen --name r-chi-square --network app-store-network r-chi-square
```

The table is stored as `gen/chi_square_table.csv`.