# syntax=docker/dockerfile:1
# check=skip=SecretsUsedInArgOrEnv
# line above is required to silence complains regarding a password variable in env.


FROM postgres:15.14-trixie

# Set environment variables for postgresql (password does not really matter for local only)
ENV POSTGRES_DB=app_store
ENV POSTGRES_USER=postgres
ENV POSTGRES_PASSWORD=password

# Install wget for fetching database dump
RUN apt-get update && apt-get install -y --no-install-recommends wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Download the dump file and init script to the container
RUN wget "https://zenodo.org/records/17037785/files/app_store_data.pgdump?download=1" -O /docker-entrypoint-initdb.d/app_store_data.pgdump
COPY 01-restore-dump.sh /docker-entrypoint-initdb.d/01-restore-dump.sh
RUN chmod +x /docker-entrypoint-initdb.d/01-restore-dump.sh

# Expose PostgreSQL port
EXPOSE 5432

# The default CMD from the base image will start postgresql
