import os


# api.runtime validates these settings while the application is imported.
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-with-at-least-thirty-two-bytes")
os.environ.setdefault("NODE_ENV", "production")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/savia_test")
