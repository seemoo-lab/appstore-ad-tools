#!/bin/bash
set -e

# Wait for PostgreSQL to be ready
until pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"; do
  echo "Waiting for PostgreSQL to be ready..."
  sleep 2
done

echo "Restoring database from dump file..."
pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v /docker-entrypoint-initdb.d/app_store_data.pgdump
echo "Database restoration completed!"
