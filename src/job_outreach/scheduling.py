import asyncio

from apscheduler.schedulers.blocking import BlockingScheduler

from job_outreach.workflows import Conflict, discover, exclusive


def serve(db, config):
    # This dedicated process is the only scheduler. Advisory lock spans its lifetime.
    scheduler = BlockingScheduler(timezone=config.timezone)

    def run():
        try:
            asyncio.run(discover(db, config))
        except Conflict:
            pass

    scheduler.add_job(
        run,
        "cron",
        hour=config.schedule_hour,
        minute=0,
        id="discovery",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    with exclusive(db, 3):
        scheduler.start()
