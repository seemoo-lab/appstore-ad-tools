# syntax=docker/dockerfile:1


FROM r-base:4.5.1

# Install system dependencies for RPostgres
RUN apt-get update && apt-get install -y \
    libpq-dev \
    libcurl4-openssl-dev \
    libxml2-dev \
    r-cran-dplyr \
    r-cran-dbi \
    r-cran-xtable \
    r-cran-tidyr \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir /usr/local/src/gen
COPY generate_chi_square_table.r /usr/local/src/
COPY *.r /usr/local/src/r_scripts/
COPY r_env /usr/local/.env
WORKDIR /usr/local/src/
CMD ["Rscript", "generate_chi_square_table.r"]