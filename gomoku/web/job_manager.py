"""Job queue manager for tournament execution."""

import logging
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy import and_, or_

from .models import db, Tournament, TournamentJob, WorkerProcess

logger = logging.getLogger(__name__)


class JobManager:
    """Manages the tournament job queue with single tournament constraint."""
    
    def __init__(self):
        self.heartbeat_timeout = 300  # 5 minutes
        self.job_timeout = 3600  # 1 hour default
    
    def create_tournament_job(self, tournament_id: int, priority: int = 0) -> Optional[TournamentJob]:
        """
        Create a new tournament job, but only if no other tournament is running.
        Enforces single tournament constraint.
        """
        try:
            # Check if any tournament is currently running
            running_job = self.get_active_tournament_job()
            if running_job:
                logger.warning(f"Cannot create job for tournament {tournament_id}: "
                              f"Tournament {running_job.tournament_id} is already running")
                return None
            
            # Check if tournament already has a job
            existing_job = TournamentJob.query.filter_by(tournament_id=tournament_id).first()
            if existing_job:
                if existing_job.status in ['pending', 'running']:
                    logger.info(f"Tournament {tournament_id} already has active job {existing_job.id}")
                    return existing_job
                elif existing_job.status == 'failed' and existing_job.retry_count < existing_job.max_retries:
                    # Reset failed job for retry
                    existing_job.status = 'pending'
                    existing_job.retry_count += 1
                    existing_job.error_message = None
                    existing_job.worker_id = None
                    db.session.commit()
                    logger.info(f"Reset failed job {existing_job.id} for retry (attempt {existing_job.retry_count})")
                    return existing_job
            
            # Create new job
            job = TournamentJob(
                tournament_id=tournament_id,
                priority=priority,
                timeout_seconds=self.job_timeout
            )
            
            db.session.add(job)
            db.session.commit()
            
            logger.info(f"Created tournament job {job.id} for tournament {tournament_id}")
            return job
            
        except Exception as e:
            logger.error(f"Error creating tournament job: {e}")
            db.session.rollback()
            return None
    
    def get_next_job(self, worker_id: str) -> Optional[TournamentJob]:
        """
        Get the next pending job for a worker.
        Enforces single tournament constraint - only one job can be running at a time.
        """
        try:
            # Check if any job is currently running
            running_job = (TournamentJob.query
                          .filter_by(status='running')
                          .first())
            
            if running_job:
                # Check if the running job is healthy
                if self._is_job_healthy(running_job):
                    logger.debug(f"Job {running_job.id} is running and healthy, no new job assigned")
                    return None
                else:
                    # Running job is unhealthy, mark it as failed and allow new job
                    logger.warning(f"Job {running_job.id} is unhealthy, marking as failed")
                    self._mark_job_failed(running_job, "Worker heartbeat timeout")
            
            # Get next pending job with highest priority
            job = (TournamentJob.query
                   .filter_by(status='pending')
                   .order_by(TournamentJob.priority.desc(), TournamentJob.created_at.asc())
                   .first())
            
            if job:
                # Assign job to worker
                job.status = 'running'
                job.worker_id = worker_id
                job.started_at = datetime.utcnow()
                job.last_heartbeat = datetime.utcnow()
                
                db.session.commit()
                
                logger.info(f"Assigned job {job.id} (tournament {job.tournament_id}) to worker {worker_id}")
                return job
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting next job: {e}")
            db.session.rollback()
            return None
    
    def update_job_heartbeat(self, job_id: str) -> bool:
        """Update heartbeat for a running job."""
        try:
            job = TournamentJob.query.get(job_id)
            if job and job.status == 'running':
                job.last_heartbeat = datetime.utcnow()
                db.session.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating job heartbeat: {e}")
            return False
    
    def complete_job(self, job_id: str, success: bool = True, error_message: str = None) -> bool:
        """Mark a job as completed or failed."""
        try:
            job = TournamentJob.query.get(job_id)
            if not job:
                logger.error(f"Job {job_id} not found")
                return False
            
            job.completed_at = datetime.utcnow()
            
            if success:
                job.status = 'completed'
                logger.info(f"Job {job_id} completed successfully")
                
                # Update worker statistics
                if job.worker_id:
                    worker = WorkerProcess.query.get(job.worker_id)
                    if worker:
                        worker.jobs_completed += 1
                        worker.current_job_id = None
            else:
                job.status = 'failed'
                job.error_message = error_message
                logger.error(f"Job {job_id} failed: {error_message}")
                
                # Update worker statistics
                if job.worker_id:
                    worker = WorkerProcess.query.get(job.worker_id)
                    if worker:
                        worker.jobs_failed += 1
                        worker.current_job_id = None
            
            db.session.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error completing job: {e}")
            db.session.rollback()
            return False
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or running job."""
        try:
            job = TournamentJob.query.get(job_id)
            if not job:
                return False
            
            if job.status in ['pending', 'running']:
                job.status = 'cancelled'
                job.completed_at = datetime.utcnow()
                job.error_message = "Cancelled by user"
                
                # Update worker
                if job.worker_id:
                    worker = WorkerProcess.query.get(job.worker_id)
                    if worker:
                        worker.current_job_id = None
                
                db.session.commit()
                logger.info(f"Cancelled job {job_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error cancelling job: {e}")
            return False
    
    def get_active_tournament_job(self) -> Optional[TournamentJob]:
        """Get the currently active (running) tournament job."""
        return (TournamentJob.query
                .filter_by(status='running')
                .first())
    
    def get_queue_status(self) -> dict:
        """Get current queue status."""
        try:
            pending_jobs = TournamentJob.query.filter_by(status='pending').count()
            running_jobs = TournamentJob.query.filter_by(status='running').count()
            completed_jobs = TournamentJob.query.filter_by(status='completed').count()
            failed_jobs = TournamentJob.query.filter_by(status='failed').count()
            
            return {
                'pending': pending_jobs,
                'running': running_jobs,
                'completed': completed_jobs,
                'failed': failed_jobs,
                'total': pending_jobs + running_jobs + completed_jobs + failed_jobs
            }
        except Exception as e:
            logger.error(f"Error getting queue status: {e}")
            return {}
    
    def cleanup_stale_jobs(self) -> int:
        """Clean up stale running jobs whose workers have died."""
        try:
            stale_threshold = datetime.utcnow() - timedelta(seconds=self.heartbeat_timeout)
            
            stale_jobs = (TournamentJob.query
                         .filter_by(status='running')
                         .filter(or_(
                             TournamentJob.last_heartbeat < stale_threshold,
                             TournamentJob.last_heartbeat.is_(None)
                         ))
                         .all())
            
            count = 0
            for job in stale_jobs:
                self._mark_job_failed(job, "Worker heartbeat timeout - job cleanup")
                count += 1
            
            if count > 0:
                logger.warning(f"Cleaned up {count} stale jobs")
            
            return count
            
        except Exception as e:
            logger.error(f"Error cleaning up stale jobs: {e}")
            return 0
    
    def _is_job_healthy(self, job: TournamentJob) -> bool:
        """Check if a job is healthy based on heartbeat."""
        if not job.last_heartbeat:
            return False
        
        time_since_heartbeat = (datetime.utcnow() - job.last_heartbeat).total_seconds()
        return time_since_heartbeat < self.heartbeat_timeout
    
    def _mark_job_failed(self, job: TournamentJob, error_message: str):
        """Mark a job as failed."""
        job.status = 'failed'
        job.error_message = error_message
        job.completed_at = datetime.utcnow()
        
        # Update worker
        if job.worker_id:
            worker = WorkerProcess.query.get(job.worker_id)
            if worker:
                worker.jobs_failed += 1
                worker.current_job_id = None
        
        db.session.commit()