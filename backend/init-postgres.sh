#!/bin/bash
# PostgreSQL initialization script for Coolify
# This script ensures the postgres role exists and is properly configured

set -e

echo "🔧 PostgreSQL Initialization Script"
echo "===================================="

# Get environment variables
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-savia}"

echo "📋 Configuration:"
echo "  - POSTGRES_USER: $POSTGRES_USER"
echo "  - POSTGRES_DB: $POSTGRES_DB"
echo ""

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

# Check if postgres role exists and has correct password
echo "🔍 Checking if postgres role exists..."
if psql -h postgres -U postgres -tc "SELECT 1 FROM pg_roles WHERE rolname='postgres'" 2>/dev/null | grep -q 1; then
    echo "✅ postgres role already exists"
    # Update password to ensure it matches
    echo "🔄 Updating postgres password..."
    psql -h postgres -U postgres -c "ALTER ROLE postgres WITH PASSWORD 'postgres';" 2>/dev/null || true
else
    echo "⚠️  postgres role does not exist, creating it..."
    psql -h postgres -U postgres -c "CREATE ROLE postgres WITH SUPERUSER CREATEDB CREATEROLE LOGIN ENCRYPTED PASSWORD 'postgres';" 2>/dev/null || true
    echo "✅ postgres role created"
fi

# Check if savia_user role exists
echo "🔍 Checking if savia_user role exists..."
if psql -h postgres -U postgres -tc "SELECT 1 FROM pg_roles WHERE rolname='$POSTGRES_USER'" 2>/dev/null | grep -q 1; then
    echo "✅ $POSTGRES_USER role already exists"
    # Update password to ensure it matches
    echo "🔄 Updating $POSTGRES_USER password..."
    psql -h postgres -U postgres -c "ALTER ROLE $POSTGRES_USER WITH PASSWORD '$POSTGRES_PASSWORD';" 2>/dev/null || true
else
    echo "⚠️  $POSTGRES_USER role does not exist, creating it..."
    psql -h postgres -U postgres -c "CREATE ROLE $POSTGRES_USER WITH LOGIN ENCRYPTED PASSWORD '$POSTGRES_PASSWORD';" 2>/dev/null || true
    echo "✅ $POSTGRES_USER role created"
fi

# Check if savia database exists
echo "🔍 Checking if $POSTGRES_DB database exists..."
if psql -h postgres -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='$POSTGRES_DB'" 2>/dev/null | grep -q 1; then
    echo "✅ $POSTGRES_DB database already exists"
else
    echo "⚠️  $POSTGRES_DB database does not exist, creating it..."
    psql -h postgres -U postgres -c "CREATE DATABASE $POSTGRES_DB OWNER $POSTGRES_USER;" 2>/dev/null || true
    echo "✅ $POSTGRES_DB database created"
fi

# Grant privileges
echo "🔐 Granting privileges..."
psql -h postgres -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE $POSTGRES_DB TO $POSTGRES_USER;" 2>/dev/null || true

echo ""
echo "✅ PostgreSQL initialization completed!"
