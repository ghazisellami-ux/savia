#!/bin/bash
# PostgreSQL initialization script for Coolify
# This script ensures the postgres role exists and is properly configured

set -e

echo "🔧 PostgreSQL Initialization Script"
echo "===================================="

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL to be ready..."
for i in {1..30}; do
    if pg_isready -h postgres -U postgres 2>/dev/null; then
        echo "✅ PostgreSQL is ready"
        break
    fi
    echo "  Attempt $i/30..."
    sleep 2
done

# Check if postgres role exists
echo "🔍 Checking if postgres role exists..."
if psql -h postgres -U postgres -tc "SELECT 1 FROM pg_roles WHERE rolname='postgres'" 2>/dev/null | grep -q 1; then
    echo "✅ postgres role already exists"
else
    echo "⚠️  postgres role does not exist, creating it..."
    psql -h postgres -U postgres -c "CREATE ROLE postgres WITH SUPERUSER CREATEDB CREATEROLE LOGIN ENCRYPTED PASSWORD 'postgres';" 2>/dev/null || true
    echo "✅ postgres role created"
fi

# Check if savia_user role exists
echo "🔍 Checking if savia_user role exists..."
if psql -h postgres -U postgres -tc "SELECT 1 FROM pg_roles WHERE rolname='savia_user'" 2>/dev/null | grep -q 1; then
    echo "✅ savia_user role already exists"
else
    echo "⚠️  savia_user role does not exist, creating it..."
    psql -h postgres -U postgres -c "CREATE ROLE savia_user WITH LOGIN ENCRYPTED PASSWORD '${POSTGRES_PASSWORD:-savia_password}';" 2>/dev/null || true
    echo "✅ savia_user role created"
fi

# Check if savia database exists
echo "🔍 Checking if savia database exists..."
if psql -h postgres -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='savia'" 2>/dev/null | grep -q 1; then
    echo "✅ savia database already exists"
else
    echo "⚠️  savia database does not exist, creating it..."
    psql -h postgres -U postgres -c "CREATE DATABASE savia OWNER savia_user;" 2>/dev/null || true
    echo "✅ savia database created"
fi

echo ""
echo "✅ PostgreSQL initialization completed!"
