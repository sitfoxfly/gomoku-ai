"""Tournament recovery system for handling crashes and restarts."""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from .models import db, Tournament, TournamentJob, WorkerProcess, TournamentCheckpoint
from .job_manager import JobManager

logger = logging.getLogger(__name__)


class TournamentRecovery:
    """Handles tournament recovery on application startup and worker failures."""
    
    def __init__(self):
        self.job_manager = JobManager()
        self.stale_timeout = timedelta(minutes=10)  # 10 minutes without heartbeat = stale
    
    def recover_on_startup(self) -> dict:
        """
        Perform recovery operations when the application starts.
        Returns dictionary with recovery statistics.
        """
        logger.info("Starting tournament recovery process...")
        
        recovery_stats = {
            'stale_workers_cleaned': 0,
            'stale_jobs_recovered': 0,
            'tournaments_requeued': 0,
            'orphaned_jobs_cleaned': 0,
            'data_inconsistencies_fixed': 0
        }
        
        try:
            # 1. Clean up stale workers
            recovery_stats['stale_workers_cleaned'] = self._cleanup_stale_workers()
            
            # 2. Handle stale/orphaned jobs
            recovery_stats['stale_jobs_recovered'] = self._recover_stale_jobs()
            recovery_stats['orphaned_jobs_cleaned'] = self._cleanup_orphaned_jobs()
            
            # 3. Re-queue interrupted tournaments
            recovery_stats['tournaments_requeued'] = self._requeue_interrupted_tournaments()
            
            # 4. Fix data inconsistencies
            recovery_stats['data_inconsistencies_fixed'] = self._fix_data_inconsistencies()
            
            logger.info(f"Tournament recovery completed: {recovery_stats}")
            return recovery_stats
            
        except Exception as e:
            logger.error(f"Error during recovery: {e}")
            return recovery_stats
    
    def _cleanup_stale_workers(self) -> int:
        """Clean up workers that haven't sent heartbeats recently."""
        try:
            stale_threshold = datetime.utcnow() - self.stale_timeout
            
            stale_workers = (WorkerProcess.query
                           .filter(WorkerProcess.last_heartbeat < stale_threshold)
                           .filter_by(status='active')
                           .all())
            
            count = 0
            for worker in stale_workers:
                logger.warning(f"Marking stale worker {worker.id} as crashed")
                worker.status = 'crashed'
                
                # If worker had a current job, mark it as failed
                if worker.current_job_id:
                    job = TournamentJob.query.get(worker.current_job_id)
                    if job and job.status == 'running':
                        logger.warning(f"Marking job {job.id} as failed due to worker crash")
                        job.status = 'failed'
                        job.error_message = f"Worker {worker.id} crashed or became unresponsive"
                        job.completed_at = datetime.utcnow()
                
                worker.current_job_id = None
                count += 1
            
            if count > 0:
                db.session.commit()
                logger.info(f"Cleaned up {count} stale workers")
            
            return count
            
        except Exception as e:
            logger.error(f"Error cleaning up stale workers: {e}")
            db.session.rollback()
            return 0
    
    def _recover_stale_jobs(self) -> int:
        """Recover jobs that were running but lost their workers."""
        try:
            # Find running jobs without healthy workers
            stale_jobs = (TournamentJob.query
                         .filter_by(status='running')
                         .all())
            
            recovered_count = 0
            
            for job in stale_jobs:
                # Check if the job's worker is still healthy
                if job.worker_id:
                    worker = WorkerProcess.query.get(job.worker_id)
                    if worker and worker.is_healthy():
                        continue  # Job is still running on healthy worker
                
                # Job is orphaned or has unhealthy worker
                logger.warning(f"Recovering stale job {job.id} for tournament {job.tournament_id}")
                
                # Check if we should retry
                if job.retry_count < job.max_retries:
                    # Reset job for retry
                    job.status = 'pending'
                    job.worker_id = None
                    job.started_at = None
                    job.last_heartbeat = None
                    job.retry_count += 1
                    job.error_message = "Recovered from worker failure"
                    
                    recovered_count += 1
                    logger.info(f"Job {job.id} reset for retry (attempt {job.retry_count})")
                else:
                    # Too many retries, mark as failed
                    job.status = 'failed'
                    job.error_message = f"Max retries ({job.max_retries}) exceeded"
                    job.completed_at = datetime.utcnow()
                    
                    # Also mark tournament as failed
                    tournament = Tournament.query.get(job.tournament_id)
                    if tournament and tournament.status == 'running':
                        tournament.status = 'failed'
                        tournament.completed_at = datetime.utcnow()
                    
                    logger.error(f"Job {job.id} marked as failed after {job.max_retries} retries")
            
            if recovered_count > 0:
                db.session.commit()
                logger.info(f"Recovered {recovered_count} stale jobs")
            
            return recovered_count
            
        except Exception as e:
            logger.error(f"Error recovering stale jobs: {e}")
            db.session.rollback()
            return 0
    
    def _cleanup_orphaned_jobs(self) -> int:
        """Clean up jobs that don't have corresponding tournaments."""
        try:
            # Find jobs whose tournaments no longer exist
            orphaned_jobs = (db.session.query(TournamentJob)
                           .outerjoin(Tournament)
                           .filter(Tournament.id.is_(None))
                           .all())
            
            count = len(orphaned_jobs)
            
            if count > 0:
                for job in orphaned_jobs:
                    logger.warning(f"Removing orphaned job {job.id}")
                    db.session.delete(job)
                
                db.session.commit()
                logger.info(f"Cleaned up {count} orphaned jobs")
            
            return count
            
        except Exception as e:
            logger.error(f"Error cleaning up orphaned jobs: {e}")
            db.session.rollback()
            return 0
    
    def _requeue_interrupted_tournaments(self) -> int:
        """Re-queue tournaments that were interrupted."""
        try:
            # Find tournaments that should be running but don't have active jobs
            interrupted_tournaments = (db.session.query(Tournament)
                                     .outerjoin(TournamentJob)
                                     .filter(Tournament.status == 'running')
                                     .filter(TournamentJob.status.notin_(['pending', 'running']))
                                     .all())\
                                     
            count = 0
            
            for tournament in interrupted_tournaments:
                logger.warning(f"Re-queuing interrupted tournament {tournament.id}")
                
                # Create new job for the tournament
                job = self.job_manager.create_tournament_job(tournament.id, priority=1)  # High priority for recovery
                if job:
                    count += 1
                    logger.info(f"Created recovery job {job.id} for tournament {tournament.id}")
                else:
                    # If job creation failed, mark tournament as failed
                    tournament.status = 'failed'
                    tournament.completed_at = datetime.utcnow()
                    logger.error(f"Failed to create recovery job for tournament {tournament.id}")
            
            if count > 0:
                db.session.commit()
                logger.info(f"Re-queued {count} interrupted tournaments")
            
            return count
            
        except Exception as e:
            logger.error(f"Error re-queuing interrupted tournaments: {e}")
            db.session.rollback()
            return 0
    
    def _fix_data_inconsistencies(self) -> int:
        """Fix common data inconsistencies after crashes."""
        try:
            fixes_count = 0
            
            # Fix tournaments with status 'running' but completed timestamp
            inconsistent_tournaments = (Tournament.query
                                      .filter_by(status='running')
                                      .filter(Tournament.completed_at.isnot(None))
                                      .all())
            
            for tournament in inconsistent_tournaments:
                logger.warning(f"Fixing tournament {tournament.id} status inconsistency")
                tournament.status = 'completed'
                fixes_count += 1
            
            # Fix tournaments with status 'completed' but no completed timestamp
            incomplete_tournaments = (Tournament.query
                                    .filter_by(status='completed')
                                    .filter(Tournament.completed_at.is_(None))
                                    .all())
            
            for tournament in incomplete_tournaments:
                logger.warning(f"Adding missing completion timestamp for tournament {tournament.id}")
                tournament.completed_at = datetime.utcnow()
                fixes_count += 1
            
            # Fix agent game statistics inconsistencies
            # (This would require checking actual game records vs. agent stats)
            # Skipping for now as it's complex and less critical
            
            if fixes_count > 0:
                db.session.commit()
                logger.info(f"Fixed {fixes_count} data inconsistencies")
            
            return fixes_count
            
        except Exception as e:
            logger.error(f"Error fixing data inconsistencies: {e}")
            db.session.rollback()
            return 0
    
    def get_recovery_status(self) -> dict:
        """Get current status of tournaments and jobs for monitoring."""
        try:
            status = {
                'timestamp': datetime.utcnow().isoformat(),
                'tournaments': {
                    'pending': Tournament.query.filter_by(status='pending').count(),
                    'running': Tournament.query.filter_by(status='running').count(),
                    'completed': Tournament.query.filter_by(status='completed').count(),
                    'failed': Tournament.query.filter_by(status='failed').count(),
                    'cancelled': Tournament.query.filter_by(status='cancelled').count()
                },
                'jobs': {
                    'pending': TournamentJob.query.filter_by(status='pending').count(),
                    'running': TournamentJob.query.filter_by(status='running').count(),
                    'completed': TournamentJob.query.filter_by(status='completed').count(),
                    'failed': TournamentJob.query.filter_by(status='failed').count(),
                    'cancelled': TournamentJob.query.filter_by(status='cancelled').count()
                },
                'workers': {
                    'active': WorkerProcess.query.filter_by(status='active').count(),
                    'inactive': WorkerProcess.query.filter_by(status='inactive').count(),
                    'crashed': WorkerProcess.query.filter_by(status='crashed').count()
                }
            }
            
            # Add health information
            healthy_workers = 0
            for worker in WorkerProcess.query.filter_by(status='active').all():
                if worker.is_healthy():
                    healthy_workers += 1
            
            status['workers']['healthy'] = healthy_workers
            status['workers']['unhealthy'] = status['workers']['active'] - healthy_workers
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting recovery status: {e}")
            return {'error': str(e)}
    
    def force_cleanup_tournament(self, tournament_id: int) -> bool:
        """Force cleanup of a specific tournament and its jobs."""
        try:
            tournament = Tournament.query.get(tournament_id)
            if not tournament:
                return False
            
            logger.info(f"Force cleaning up tournament {tournament_id}")
            
            # Cancel/clean up any associated jobs
            jobs = TournamentJob.query.filter_by(tournament_id=tournament_id).all()
            for job in jobs:
                if job.status in ['pending', 'running']:
                    job.status = 'cancelled'
                    job.error_message = 'Force cancelled by administrator'
                    job.completed_at = datetime.utcnow()
                    
                    # Update worker if assigned
                    if job.worker_id:
                        worker = WorkerProcess.query.get(job.worker_id)
                        if worker:
                            worker.current_job_id = None
            
            # Reset tournament status
            tournament.status = 'cancelled'
            tournament.completed_at = datetime.utcnow()
            
            db.session.commit()
            logger.info(f"Force cleanup completed for tournament {tournament_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error force cleaning tournament {tournament_id}: {e}")
            db.session.rollback()
            return False