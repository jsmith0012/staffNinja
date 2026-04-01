"""jobs package — background job queue for staffNinja."""

from jobs.queue import enqueue, get_job, pending_count, reap_stale_jobs, job_counts, recent_failed  # noqa: F401
from jobs.handlers import register, get_handler, registered_types  # noqa: F401
from jobs.worker import Worker  # noqa: F401
from jobs.scheduler import Scheduler  # noqa: F401

# Import built-in handlers so they register on module load
import jobs.builtin_handlers  # noqa: F401
