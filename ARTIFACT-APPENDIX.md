# Artifact Appendix

Paper title: **Ad Personalization and Transparency in Mobile Ecosystems: A Comparative Analysis of Google's and Apple's EU App Stores**

Requested Badge(s):
  - [x] **Available**
  - [x] **Functional**
  - [x] **Reproduced**

## Description
Artifact for the paper **Ad Personalization and Transparency in Mobile Ecosystems: A Comparative Analysis of Google's and Apple's EU App Stores** by David Breuer, Lucas Becker, and Matthias Hollick, to appear in the Proceedings on Privacy Enhancing Technologies 2026(1).

This artifact includes our full instrumentation code to measure advertisements on physical Android and iOS smartphones, covering the end-to-end pipeline from device setup to device reset. Additionally, it contains our API backend for central measurement data storage, with some helper scripts for persona management and the creation of Google and Apple accounts.

Finally, we provide an export of our raw measurement data together with scripts to fully reproduce all figures and tables derived from our data.

### Security/Privacy Issues and Ethical Concerns
To the best of our knowledge, there are no privacy or security risks while running the artifact evaluation.

## Basic Requirements

### Hardware Requirements

Can run on a laptop (No special hardware requirements).

The experiment described in the following sections were performed an off-the-shelf MacBook Pro (arm64) and a Linux ThinkPad (x86_64).

### Software Requirements

OS Version: Nothing special needed. We tested everything on macOS 15.6.1 (arm64) and Debian 6.12.38-1 (x86_64).

Needed OS Packages: 
- Python >= 3.12 
- R >= 4.5.1
- Docker 28.3.3 (containerd 1.7.27)
- All Python requirements are documented in `requirements.txt` files alongside the python scripts.
- All R requirements are automatically installed as part of the R scripts.
- Our dataset can be downloaded here (https://doi.org/10.5281/zenodo.17037784). It is automatically downloaded by the provided postgres docker container.

### Estimated Time and Storage Consumption

Overall human time: < 10 minutes
Overall compute time: 1.5 hours
Overall disk space: < 5GB


## Environment
In the following, we describe the environment setup for using this artifact.

### Accessibility
- Source Code Repository: [Github](https://github.com/seemoo-lab/appstore-ad-tools).
- Dataset: [Zenodo](https://doi.org/10.5281/zenodo.17037784).
  _Note:_ The dataset is automatically fetched by the provided Docker container but can be used in isolation as well.

### Set up the environment
1. Check out the repository and start the database container
```bash
git clone https://github.com/seemoo-lab/appstore-ad-tools.git
cd appstore-ad-tools
# For both experiments the provided docker container, including our database needs to be built and running:
# To build and start the docker container serving the database, run:
docker network create app-store-network
docker build -t postgres-app-store stats-and-figures/database
docker run -d --name postgres-app-store -p 5432:5432 --network app-store-network postgres-app-store
```

2. Configure environmental variables:  
   Copy sample.env to .env and set values to reflect your environment:
     You can leave the default `DB_*`values if you use our docker container.
```sh
cp sample.env .env
```

3. Configure python-venv and install python dependencies
```sh
python3 -m venv stats-and-figures/.venv
source stats-and-figures/.venv/bin/activate
pip install -r stats-and-figures/requirements.txt
```

### Testing the Environment
You can check that everything is configured correctly by executing the following script:
```sh
python stats-and-figures/test_environment.py
```

Expected output:
```
Everything is set up :)
```

## Artifact Evaluation

### Main Results and Claims

#### Main Result 1: Permutation Tests (Table 1 of the paper)
The artifact reproduces Table 1 of our paper. 

Our code computes permutation tests of all our experiments with chi-square as test statistic (R = 9999).
The results are summarized by Table 1 by stating how many of our experiments show statistical significance (p <= 0.05).

From this result, we claim significant differences between the advertisement and recommender systems of Apple and Google.

#### Main Result 2: Personalization Characteristics
In our paper, we test the effect of different personas on the ads they receive. One indicator of such effects are the category and item frequencies. For better interpretability, we depict these values in multiple Figures using different aspects.

The artifact produces Figures 4 to 9 of our paper.


### Experiments

#### Experiment 1: Permutation Tests (Table 1 of the paper)
You can run the following docker container to recreate Table 1 of our paper.
This command takes approx. 1 hour to complete.
```sh
docker build -t r-chi-square stats-and-figures/r_scripts
docker run -v stats-and-figures/gen:/usr/local/src/gen --name r-chi-square --network app-store-network r-chi-square
```

The table is stored as `stats-and-figures/gen/chi_square_table.csv`.

The resulting table is stored as `gen/chi_square_table.csv` and resembles Table 1 of our paper.

#### Experiment 2: Generating Figures
Run the `generate_plots.py` script to generate Figures 4 to 9:
```bash
python3 stats-and-figures/database/generate_plots.py
```
The resulting figure files are written to `gen/`.


## Limitations
The provided evaluation instructions reproduce Table 1 and all figures of our paper from of our provided dataset.

The dataset itself cannot be reproduced because of the following reasons:
- Complex hardware setup needed (See Section 4.4 of our paper).
- Conducting the study requires more than 200 eSIMs, and 249 Apple and Google Accounts. Creating and maintaining those accounts requires a lot of manual effort. 
- The study itself takes approx. 3 weeks to conduct and needs close supervision.

Nevertheless, we provide all code that was used to create the dataset. With this, other researchers can inspect similar platforms on smartphones.

## Notes on Reusability
With our artifact, we provide an instrumentation framework to run automated experiments on Android smartphones and iPhones. Fellow researchers can use our codebase to instrument their own devices and run experiments on app stores or other smartphone-first platforms.
It may be used to just remotely reset and set up smartphones, or to run complex automated UI interactions on arbitrary platforms.
