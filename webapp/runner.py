import sqlite3
import time
import signal
import threading
from aalib.progress import progress
from aalib.colors import FMT

from webapp.classify import get_ollama, process_item
from webapp.db import items_left_in_job, get_connection, remaining_items_count

class JobWorker:
    """
    Processes jobs in order of creation.
    """
    def __init__(self):
        self.current_job_id = None

    def start(self):
        """Main worker loop. Registers signal handlers and begins processing jobs."""
        signal.signal(signal.SIGINT, self._handle_exit)
        signal.signal(signal.SIGTERM, self._handle_exit)

        while True:
            job = self._claim_next_job()

            if job is not None:
                self._process_job(*job)
            else:
                print("waiting...")
                time.sleep(.5)

    def _claim_next_job(self) -> tuple[str, str, str, str, int, float, int] | None:
        try:
            conn = get_connection()
            conn.execute("BEGIN EXCLUSIVE")
            row = conn.execute("""
                SELECT id, name, model, prompt, repeats, time_taken, num_completed FROM jobs
                WHERE status = 'WAITING'
                ORDER BY time_created ASC
                LIMIT 1
            """).fetchone()

            if row:
                job_id, name, model, prompt, repeats, time_taken, completed = row
                start_time = time.time()
                conn.execute("""
                    UPDATE jobs
                    SET status = 'RUNNING', time_started = ?
                    WHERE id = ?
                """, (start_time, job_id))
                conn.commit()
                self.current_job_id = job_id
                print(f"Claimed job {job_id}")
                return job_id, name, model, prompt, repeats, time_taken, completed
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Error claiming job: {e}")
        return None


    def _check_alive(self, job_id: str, conn: sqlite3.Connection):
        x = conn.execute('SELECT status FROM jobs WHERE id = ?', (job_id,)).fetchone()
        if x is None:
            return False
        if x[0] != 'RUNNING':
            return False
        return True


    def _process_job(self, job_id: str, name: str, model: str, prompt: str, repeats: int, time_taken: float, completed: int):
        try:
            client = get_ollama()
            conn = get_connection()

            for item in progress(items_left_in_job(job_id, repeats), count=remaining_items_count(job_id, repeats), message=f'{name} ({model})', color=FMT.BLUE):
                t0 = time.time()
                if process_item(conn, client, job_id, name, model, prompt, item):
                    completed += 1

                time_taken += time.time() - t0
                self._update_job_progress(job_id, completed, time_taken)
                if not self._check_alive(job_id, conn):
                    return

            self._finalize_job(job_id)
            self.current_job_id = None
        except:
            self._pause_current_job()
            raise

    def _update_job_progress(self, job_id: str, num_completed: int, time_taken: float):
        conn = get_connection()
        try:
            conn.execute("""
                UPDATE jobs
                SET time_taken = ?, num_completed = ?
                WHERE id = ?
            """, (time_taken, num_completed, job_id))
            conn.commit()
        except Exception as e:
            print(f"Error updating job progress for job {job_id}: {e}")

    def _finalize_job(self, job_id: str):
        conn = get_connection()
        try:
            conn.execute("""
                UPDATE jobs
                SET status = 'FINISHED'
                WHERE id = ?
            """, (job_id,))
            conn.commit()
        except Exception as e:
                print(f"Error finalizing job {job_id}: {e}")

    def _pause_current_job(self):
        job_id = self.current_job_id
        if job_id:
            try:
                conn = get_connection()
                conn.execute("""
                    UPDATE jobs
                    SET status = 'PAUSED'
                    WHERE id = ? AND status = 'RUNNING'
                """, (job_id,))
                conn.commit()
                print(f"Job {job_id} paused due to shutdown.")
                self.current_job_id = None
            except Exception as e:
                print(f"Error pausing job {job_id}: {e}")

    def _handle_exit(self, signum, frame):
        """Signal handler for graceful shutdown."""
        print("Interrupt received, cleaning up...")
        self._pause_current_job()
        raise SystemExit()

    def __del__(self):
        self._pause_current_job()

if __name__ == '__main__':
    w=JobWorker()
    try:
        w.start()
    except:
        del w
        raise

