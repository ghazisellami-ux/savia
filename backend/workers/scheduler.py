"""Dedicated entry point for SAVIA's scheduled jobs.

Run this process once per deployment with ``python -m workers.scheduler``.
PostgreSQL advisory locking still protects the work if it is accidentally
scaled to multiple replicas.
"""

from services.scheduled_jobs import run_scheduler_forever


if __name__ == "__main__":
    run_scheduler_forever()
