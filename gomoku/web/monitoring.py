"""Health monitoring system for tournament workers and jobs."""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable

from flask import current_app, has_app_context
from .models import db, WorkerProcess, TournamentJob, Tournament
from .job_manager import JobManager
from .recovery import TournamentRecovery

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Monitors worker health and automatically handles failures."""
    
    def __init__(self, 
                 check_interval: int = 60,  # Check every minute
                 worker_timeout: int = 300,  # 5 minutes timeout
                 job_timeout: int = 3600):   # 1 hour job timeout
        self.check_interval = check_interval
        self.worker_timeout = worker_timeout
        self.job_timeout = job_timeout
        
        self.job_manager = JobManager()
        self.recovery = TournamentRecovery()
        
        # Monitoring state
        self.running = False
        self.monitor_thread = None
        
        # Callbacks for notifications
        self.worker_failure_callbacks: List[Callable] = []
        self.job_failure_callbacks: List[Callable] = []
        self.recovery_callbacks: List[Callable] = []
    
    def start_monitoring(self):
        """Start the health monitoring thread."""
        if self.running:
            logger.warning("Health monitoring is already running")
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        logger.info(f"Health monitoring started (check_interval={self.check_interval}s)")
    
    def stop_monitoring(self):
        """Stop the health monitoring thread."""
        if not self.running:
            return
        
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=10)
        
        logger.info("Health monitoring stopped")
    
    def add_worker_failure_callback(self, callback: Callable):
        """Add callback for worker failure notifications."""
        self.worker_failure_callbacks.append(callback)
    
    def add_job_failure_callback(self, callback: Callable):
        """Add callback for job failure notifications."""
        self.job_failure_callbacks.append(callback)
    
    def add_recovery_callback(self, callback: Callable):
        """Add callback for recovery notifications."""
        self.recovery_callbacks.append(callback)
    
    def _monitor_loop(self):
        """Main monitoring loop."""
        logger.info("Health monitoring loop started")
        
        while self.running:
            try:
                # Check if we have an application context
                if not has_app_context():
                    logger.debug("No Flask application context available, skipping health checks")
                    time.sleep(self.check_interval)
                    continue
                
                # Perform health checks
                self._check_worker_health()
                self._check_job_health()
                self._check_tournament_consistency()
                
                # Perform automatic cleanup
                self._cleanup_stale_entities()
                
                # Sleep until next check
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(self.check_interval)
        
        logger.info("Health monitoring loop ended")
    
    def _check_worker_health(self):
        """Check health of all active workers."""
        if not has_app_context():
            return
        try:
            timeout_threshold = datetime.utcnow() - timedelta(seconds=self.worker_timeout)
            
            # Get workers that should be active but haven't sent heartbeat recently
            unhealthy_workers = (WorkerProcess.query
                               .filter_by(status='active')
                               .filter(WorkerProcess.last_heartbeat < timeout_threshold)
                               .all())
            
            for worker in unhealthy_workers:
                logger.warning(f"Worker {worker.id} is unhealthy (last heartbeat: {worker.last_heartbeat})")
                self._handle_worker_failure(worker)
                
        except Exception as e:
            logger.error(f"Error checking worker health: {e}")
    
    def _check_job_health(self):
        """Check health of running jobs."""
        if not has_app_context():
            return
        try:
            timeout_threshold = datetime.utcnow() - timedelta(seconds=self.job_timeout)
            
            # Get jobs that have been running too long without completion
            stuck_jobs = (TournamentJob.query
                         .filter_by(status='running')
                         .filter(TournamentJob.started_at < timeout_threshold)
                         .all())
            
            for job in stuck_jobs:
                logger.warning(f"Job {job.id} has been running too long (started: {job.started_at})")
                self._handle_job_timeout(job)
                
        except Exception as e:
            logger.error(f"Error checking job health: {e}")
    
    def _check_tournament_consistency(self):
        """Check for tournament state inconsistencies."""
        if not has_app_context():
            return
        try:
            # Check for tournaments marked as running but with no active jobs
            orphaned_tournaments = (db.session.query(Tournament)
                                  .outerjoin(TournamentJob)
                                  .filter(Tournament.status == 'running')
                                  .filter(~TournamentJob.status.in_(['pending', 'running']))
                                  .all())
            
            for tournament in orphaned_tournaments:
                logger.warning(f"Tournament {tournament.id} is marked as running but has no active job")
                self._handle_orphaned_tournament(tournament)
                
        except Exception as e:
            logger.error(f"Error checking tournament consistency: {e}")
    
    def _cleanup_stale_entities(self):
        """Clean up stale database entities."""
        if not has_app_context():
            return
        try:
            # Clean up old completed/failed jobs (keep for 7 days)
            cleanup_threshold = datetime.utcnow() - timedelta(days=7)
            
            old_jobs = (TournamentJob.query
                       .filter(TournamentJob.status.in_(['completed', 'failed', 'cancelled']))
                       .filter(TournamentJob.completed_at < cleanup_threshold)
                       .all())
            
            if old_jobs:
                count = len(old_jobs)
                for job in old_jobs:
                    db.session.delete(job)
                
                db.session.commit()
                logger.info(f"Cleaned up {count} old jobs")
            
            # Clean up old checkpoints (keep latest 5 per tournament)
            from .models import TournamentCheckpoint
            
            tournaments_with_checkpoints = (db.session.query(TournamentCheckpoint.tournament_id.distinct())
                                          .all())
            
            for (tournament_id,) in tournaments_with_checkpoints:
                checkpoints = (TournamentCheckpoint.query
                             .filter_by(tournament_id=tournament_id)
                             .order_by(TournamentCheckpoint.created_at.desc())
                             .all())
                
                if len(checkpoints) > 5:
                    # Keep latest 5, delete the rest
                    to_delete = checkpoints[5:]
                    for checkpoint in to_delete:
                        db.session.delete(checkpoint)
            
            db.session.commit()
                
        except Exception as e:
            logger.error(f"Error cleaning up stale entities: {e}")
            db.session.rollback()
    
    def _handle_worker_failure(self, worker: WorkerProcess):
        """Handle a failed worker."""
        try:
            logger.error(f"Handling failure of worker {worker.id}")
            
            # Mark worker as crashed
            worker.status = 'crashed'
            
            # Handle any job assigned to this worker
            if worker.current_job_id:
                job = TournamentJob.query.get(worker.current_job_id)
                if job and job.status == 'running':
                    logger.warning(f"Reassigning job {job.id} from failed worker")
                    
                    if job.retry_count < job.max_retries:
                        # Reset job for retry
                        job.status = 'pending'
                        job.worker_id = None
                        job.started_at = None
                        job.last_heartbeat = None
                        job.retry_count += 1
                        job.error_message = f"Worker {worker.id} failed"
                    else:
                        # Max retries reached
                        job.status = 'failed'
                        job.error_message = f"Max retries exceeded after worker {worker.id} failed"
                        job.completed_at = datetime.utcnow()
                        
                        # Mark tournament as failed too
                        tournament = Tournament.query.get(job.tournament_id)
                        if tournament and tournament.status == 'running':
                            tournament.status = 'failed'
                            tournament.completed_at = datetime.utcnow()
                
                worker.current_job_id = None
                worker.jobs_failed += 1
            
            db.session.commit()
            
            # Notify callbacks
            for callback in self.worker_failure_callbacks:
                try:
                    callback(worker)
                except Exception as e:
                    logger.error(f"Error in worker failure callback: {e}")
                    
        except Exception as e:
            logger.error(f"Error handling worker failure: {e}")
            db.session.rollback()
    
    def _handle_job_timeout(self, job: TournamentJob):
        """Handle a job that has timed out."""
        try:
            logger.error(f"Handling timeout of job {job.id}")
            
            # Mark job as failed
            job.status = 'failed'
            job.error_message = f"Job timeout after {self.job_timeout} seconds"
            job.completed_at = datetime.utcnow()
            
            # Update worker
            if job.worker_id:
                worker = WorkerProcess.query.get(job.worker_id)
                if worker:
                    worker.jobs_failed += 1
                    worker.current_job_id = None
            
            # Mark tournament as failed
            tournament = Tournament.query.get(job.tournament_id)
            if tournament and tournament.status == 'running':
                tournament.status = 'failed'
                tournament.completed_at = datetime.utcnow()
            
            db.session.commit()
            
            # Notify callbacks
            for callback in self.job_failure_callbacks:
                try:
                    callback(job)
                except Exception as e:
                    logger.error(f"Error in job failure callback: {e}")
                    
        except Exception as e:
            logger.error(f"Error handling job timeout: {e}")
            db.session.rollback()
    
    def _handle_orphaned_tournament(self, tournament: Tournament):
        """Handle a tournament that's marked as running but has no active job."""
        try:
            logger.warning(f"Handling orphaned tournament {tournament.id}")
            
            # Try to create a new job for recovery
            job = self.job_manager.create_tournament_job(tournament.id, priority=1)
            
            if job:
                logger.info(f"Created recovery job {job.id} for orphaned tournament {tournament.id}")
                
                # Notify callbacks
                for callback in self.recovery_callbacks:
                    try:
                        callback(tournament, 'job_created')
                    except Exception as e:
                        logger.error(f"Error in recovery callback: {e}")
            else:
                # Couldn't create job, mark tournament as failed
                logger.error(f"Couldn't create recovery job for tournament {tournament.id}, marking as failed")
                tournament.status = 'failed'
                tournament.completed_at = datetime.utcnow()
                db.session.commit()
                
        except Exception as e:
            logger.error(f"Error handling orphaned tournament: {e}")
    
    def get_health_status(self) -> Dict:
        """Get current health status of the system."""
        if not has_app_context():
            return {'error': 'No application context available'}
        try:
            now = datetime.utcnow()
            timeout_threshold = now - timedelta(seconds=self.worker_timeout)
            
            # Worker health
            total_workers = WorkerProcess.query.count()
            active_workers = WorkerProcess.query.filter_by(status='active').count()
            healthy_workers = (WorkerProcess.query
                             .filter_by(status='active')
                             .filter(WorkerProcess.last_heartbeat >= timeout_threshold)
                             .count())
            
            # Job health
            total_jobs = TournamentJob.query.count()
            running_jobs = TournamentJob.query.filter_by(status='running').count()
            pending_jobs = TournamentJob.query.filter_by(status='pending').count()
            failed_jobs = TournamentJob.query.filter_by(status='failed').count()
            
            # Tournament health
            running_tournaments = Tournament.query.filter_by(status='running').count()
            pending_tournaments = Tournament.query.filter_by(status='pending').count()
            
            return {
                'timestamp': now.isoformat(),
                'monitoring_active': self.running,
                'workers': {
                    'total': total_workers,
                    'active': active_workers,
                    'healthy': healthy_workers,
                    'unhealthy': active_workers - healthy_workers
                },
                'jobs': {
                    'total': total_jobs,
                    'running': running_jobs,
                    'pending': pending_jobs,
                    'failed': failed_jobs
                },
                'tournaments': {
                    'running': running_tournaments,
                    'pending': pending_tournaments
                },
                'system_health': 'healthy' if healthy_workers > 0 and failed_jobs == 0 else 'degraded'
            }
            
        except Exception as e:
            logger.error(f"Error getting health status: {e}")
            return {'error': str(e)}
    
    def force_worker_cleanup(self, worker_id: str) -> bool:
        """Force cleanup of a specific worker."""
        if not has_app_context():
            return False
        try:
            worker = WorkerProcess.query.get(worker_id)
            if not worker:
                return False
            
            logger.info(f"Force cleaning up worker {worker_id}")
            
            # Handle any current job
            if worker.current_job_id:
                job = TournamentJob.query.get(worker.current_job_id)
                if job and job.status == 'running':
                    job.status = 'failed'
                    job.error_message = 'Worker force cleaned by administrator'
                    job.completed_at = datetime.utcnow()
            
            # Mark worker as inactive
            worker.status = 'inactive'
            worker.current_job_id = None
            
            db.session.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error force cleaning worker {worker_id}: {e}")
            return False