"""Flask web application for agent submission system."""

import os
import asyncio
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, current_app
from werkzeug.utils import secure_filename
import threading

from .models import db, Agent, Tournament, Game, TournamentJob, WorkerProcess
from .validator import AgentValidator
from .tournament import TournamentRunner
from .job_manager import JobManager
from .recovery import TournamentRecovery
from .monitoring import HealthMonitor


def create_app(config=None):
    """Create and configure Flask application."""
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///gomoku_web.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
    
    if config:
        app.config.update(config)
    
    # Initialize extensions
    db.init_app(app)
    
    # Create upload directory
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Initialize components
    validator = AgentValidator(app.config['UPLOAD_FOLDER'])
    tournament_runner = TournamentRunner(app.config['UPLOAD_FOLDER'])
    job_manager = JobManager()
    recovery = TournamentRecovery()
    health_monitor = HealthMonitor()
    
    # Create tables on startup
    with app.app_context():
        db.create_all()
        
        # Perform recovery on startup
        recovery_stats = recovery.recover_on_startup()
        app.logger.info(f"Startup recovery completed: {recovery_stats}")
        
        # Start health monitoring
        health_monitor.start_monitoring()
        app.logger.info("Health monitoring started")
    
    # Routes
    @app.route('/')
    def index():
        """Main dashboard page."""
        # Get recent stats
        total_agents = Agent.query.filter_by(is_valid=True).count()
        total_games = Game.query.filter(Game.completed_at.isnot(None)).count()
        
        # Get leaderboard
        leaderboard = tournament_runner.get_leaderboard(limit=10)
        
        # Get recent games
        recent_games = tournament_runner.get_recent_games(limit=10)
        
        # Get active tournaments
        active_tournaments = Tournament.query.filter_by(status='running').all()
        
        return render_template('dashboard.html',
                             total_agents=total_agents,
                             total_games=total_games,
                             leaderboard=leaderboard,
                             recent_games=recent_games,
                             active_tournaments=active_tournaments)
    
    @app.route('/upload', methods=['GET', 'POST'])
    def upload_agent():
        """Upload agent page."""
        if request.method == 'POST':
            # Get form data
            name = request.form.get('name', '').strip()
            author = request.form.get('author', '').strip()
            description = request.form.get('description', '').strip()
            version = request.form.get('version', '1.0.0').strip()
            class_name = request.form.get('class_name', 'Agent').strip()
            
            # Validate required fields
            if not name or not author:
                flash('Name and author are required.', 'error')
                return render_template('upload.html')
            
            # Check for uploaded file
            if 'agent_file' not in request.files:
                flash('No agent file uploaded.', 'error')
                return render_template('upload.html')
            
            file = request.files['agent_file']
            if file.filename == '':
                flash('No file selected.', 'error')
                return render_template('upload.html')
            
            if not file.filename.endswith('.py'):
                flash('Agent file must be a Python (.py) file.', 'error')
                return render_template('upload.html')
            
            try:
                # Save uploaded files
                metadata = {
                    'name': name,
                    'author': author,
                    'description': description,
                    'version': version,
                    'class_name': class_name
                }
                
                success, result = validator.save_uploaded_files({'agent_file': file}, metadata)
                if not success:
                    flash(f'Upload failed: {result}', 'error')
                    return render_template('upload.html')
                
                agent_dir = result
                
                # Validate the agent
                is_valid, error_message = validator.validate_agent(agent_dir)
                
                # Create agent record
                agent = Agent(
                    name=name,
                    author=author,
                    description=description,
                    version=version,
                    file_path=agent_dir,
                    is_valid=is_valid,
                    validation_error=error_message
                )
                
                db.session.add(agent)
                db.session.commit()
                
                if is_valid:
                    flash(f'Agent "{name}" uploaded successfully!', 'success')
                else:
                    flash(f'Agent uploaded but validation failed: {error_message}', 'warning')
                
                return redirect(url_for('agent_detail', agent_id=agent.id))
                
            except Exception as e:
                flash(f'Upload error: {str(e)}', 'error')
                return render_template('upload.html')
        
        return render_template('upload.html')
    
    @app.route('/agents')
    def agents_list():
        """List all agents."""
        agents = Agent.query.order_by(Agent.uploaded_at.desc()).all()
        return render_template('agents.html', agents=agents)
    
    @app.route('/agents/<int:agent_id>')
    def agent_detail(agent_id):
        """Agent detail page."""
        agent = Agent.query.get_or_404(agent_id)
        
        # Get agent's recent games
        recent_games = (Game.query
                       .filter((Game.black_agent_id == agent_id) | (Game.white_agent_id == agent_id))
                       .filter(Game.completed_at.isnot(None))
                       .order_by(Game.completed_at.desc())
                       .limit(20)
                       .all())
        
        return render_template('agent_detail.html', agent=agent, recent_games=recent_games)
    
    @app.route('/leaderboard')
    def leaderboard():
        """Leaderboard page."""
        leaders = (Agent.query
                  .filter_by(is_valid=True)
                  .filter(Agent.games_played > 0)
                  .order_by(Agent.elo_rating.desc())
                  .limit(50)
                  .all())
        return render_template('leaderboard.html', leaders=leaders)
    
    @app.route('/tournaments')
    def tournaments_list():
        """List all tournaments."""
        tournaments = Tournament.query.order_by(Tournament.created_at.desc()).all()
        return render_template('tournaments.html', tournaments=tournaments)
    
    @app.route('/tournaments/new')
    def new_tournament():
        """Show tournament creation form with agent selection."""
        agents = Agent.query.filter_by(is_valid=True).all()
        return render_template('tournament_new.html', agents=agents)
    
    @app.route('/tournaments/create', methods=['POST'])
    def create_tournament():
        """Create and queue a new tournament."""
        try:
            # Check if another tournament is already running (single tournament constraint)
            active_job = job_manager.get_active_tournament_job()
            if active_job:
                active_tournament = Tournament.query.get(active_job.tournament_id)
                flash(f'Cannot create tournament: "{active_tournament.name}" is already running. Please wait for it to complete.', 'warning')
                return redirect(url_for('new_tournament'))
            
            # Get selected agents from form
            selected_agent_ids = request.form.getlist('selected_agents')
            tournament_name = request.form.get('tournament_name', '').strip()
            
            if not selected_agent_ids:
                flash('Please select at least 2 agents for the tournament.', 'error')
                return redirect(url_for('new_tournament'))
            
            if len(selected_agent_ids) < 2:
                flash('A tournament requires at least 2 agents.', 'error')
                return redirect(url_for('new_tournament'))
            
            # Convert to integers
            try:
                agent_ids = [int(agent_id) for agent_id in selected_agent_ids]
            except ValueError:
                flash('Invalid agent selection.', 'error')
                return redirect(url_for('new_tournament'))
            
            # Create tournament record
            tournament = tournament_runner.create_tournament(
                name=tournament_name, 
                selected_agent_ids=agent_ids
            )
            
            # Create job for tournament execution
            job = job_manager.create_tournament_job(tournament.id, priority=0)
            
            if job:
                flash(f'Tournament "{tournament.name}" created and queued for execution!', 'success')
                flash('A worker process will pick up and execute this tournament shortly.', 'info')
            else:
                flash(f'Tournament "{tournament.name}" created but failed to queue for execution.', 'warning')
            
        except Exception as e:
            flash(f'Failed to create tournament: {str(e)}', 'error')
        
        return redirect(url_for('tournaments_list'))
    
    @app.route('/tournaments/<int:tournament_id>')
    def tournament_detail(tournament_id):
        """Tournament detail page."""
        tournament = Tournament.query.get_or_404(tournament_id)
        games = (Game.query
                .filter_by(tournament_id=tournament_id)
                .order_by(Game.started_at.desc())
                .all())
        
        return render_template('tournament_detail.html', tournament=tournament, games=games)
    
    @app.route('/tournaments/<int:tournament_id>/cancel', methods=['POST'])
    def cancel_tournament(tournament_id):
        """Cancel a running tournament."""
        try:
            tournament = Tournament.query.get_or_404(tournament_id)
            
            if tournament.status == 'running':
                tournament.status = 'cancelled'
                tournament.completed_at = datetime.utcnow()
                db.session.commit()
                flash(f'Tournament "{tournament.name}" has been cancelled.', 'info')
            else:
                flash(f'Tournament "{tournament.name}" is not currently running.', 'warning')
        except Exception as e:
            flash(f'Failed to cancel tournament: {str(e)}', 'error')
        
        return redirect(url_for('tournament_detail', tournament_id=tournament_id))
    
    @app.route('/tournaments/<int:tournament_id>/delete', methods=['POST'])
    def delete_tournament(tournament_id):
        """Delete a tournament and all its games."""
        try:
            tournament = Tournament.query.get_or_404(tournament_id)
            tournament_name = tournament.name
            
            # Delete all games in this tournament first
            Game.query.filter_by(tournament_id=tournament_id).delete()
            
            # Delete the tournament
            db.session.delete(tournament)
            db.session.commit()
            
            flash(f'Tournament "{tournament_name}" and all its games have been deleted.', 'success')
        except Exception as e:
            flash(f'Failed to delete tournament: {str(e)}', 'error')
        
        return redirect(url_for('tournaments_list'))
    
    @app.route('/games/<int:game_id>')
    def game_detail(game_id):
        """Game detail page."""
        game = Game.query.get_or_404(game_id)
        
        # Try to load game log if available
        game_log = None
        if game.game_log_path and os.path.exists(game.game_log_path):
            try:
                import json
                with open(game.game_log_path, 'r') as f:
                    game_log = json.load(f)
            except Exception:
                pass
        
        return render_template('game_detail.html', game=game, game_log=game_log)
    
    @app.route('/games/<int:game_id>/html')
    def game_html_view(game_id):
        """Serve the HTML visualization for a game."""
        game = Game.query.get_or_404(game_id)
        
        if not game.game_html_path or not os.path.exists(game.game_html_path):
            # If no HTML file exists, try to generate it from the JSON log
            if game.game_log_path and os.path.exists(game.game_log_path):
                try:
                    from ..utils.json_to_html import JSONToHTMLConverter
                    import json
                    
                    # Load the JSON game data
                    with open(game.game_log_path, 'r') as f:
                        game_data = json.load(f)
                    
                    # Determine board size from metadata or default
                    board_size = game_data.get('game_metadata', {}).get('board_size', 15)
                    
                    # Generate HTML content
                    converter = JSONToHTMLConverter(board_size, show_llm_logs=True)
                    html_content = converter.generate_html(game_data)
                    
                    # Save the HTML file for future use
                    html_filename = f"game_{game.id}_{game.black_agent.name}_vs_{game.white_agent.name}.html"
                    html_path = Path(current_app.config.get('UPLOAD_FOLDER', 'uploads')) / 'game_logs' / html_filename
                    html_path.parent.mkdir(exist_ok=True)
                    
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(html_content)
                    
                    # Update the database
                    game.game_html_path = str(html_path)
                    db.session.commit()
                    
                    return html_content
                except Exception as e:
                    return f"Error generating HTML visualization: {str(e)}", 500
            else:
                return "Game visualization not available", 404
        
        # Serve the existing HTML file
        try:
            with open(game.game_html_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"Error loading HTML visualization: {str(e)}", 500
    
    # Monitoring and Admin Routes
    @app.route('/admin/system-status')
    def admin_system_status():
        """Admin page showing system status."""
        health_status = health_monitor.get_health_status()
        recovery_status = recovery.get_recovery_status()
        queue_status = job_manager.get_queue_status()
        
        # Get active workers
        workers = WorkerProcess.query.all()
        
        # Get recent jobs
        recent_jobs = (TournamentJob.query
                      .order_by(TournamentJob.created_at.desc())
                      .limit(20)
                      .all())
        
        return render_template('admin/system_status.html',
                             health_status=health_status,
                             recovery_status=recovery_status,
                             queue_status=queue_status,
                             workers=workers,
                             recent_jobs=recent_jobs)
    
    @app.route('/admin/force-cleanup-tournament/<int:tournament_id>', methods=['POST'])
    def admin_force_cleanup_tournament(tournament_id):
        """Force cleanup of a tournament."""
        success = recovery.force_cleanup_tournament(tournament_id)
        if success:
            flash(f'Tournament {tournament_id} has been force cleaned up.', 'success')
        else:
            flash(f'Failed to cleanup tournament {tournament_id}.', 'error')
        
        return redirect(url_for('admin_system_status'))
    
    @app.route('/admin/force-cleanup-worker/<worker_id>', methods=['POST'])
    def admin_force_cleanup_worker(worker_id):
        """Force cleanup of a worker."""
        success = health_monitor.force_worker_cleanup(worker_id)
        if success:
            flash(f'Worker {worker_id} has been force cleaned up.', 'success')
        else:
            flash(f'Failed to cleanup worker {worker_id}.', 'error')
        
        return redirect(url_for('admin_system_status'))
    
    # API Routes
    @app.route('/api/agents')
    def api_agents():
        """API endpoint for agents list."""
        agents = Agent.query.all()
        return jsonify([agent.to_dict() for agent in agents])
    
    @app.route('/api/leaderboard')
    def api_leaderboard():
        """API endpoint for leaderboard."""
        limit = request.args.get('limit', 50, type=int)
        leaders = tournament_runner.get_leaderboard(limit=limit)
        return jsonify(leaders)
    
    @app.route('/api/games/recent')
    def api_recent_games():
        """API endpoint for recent games."""
        limit = request.args.get('limit', 20, type=int)
        games = tournament_runner.get_recent_games(limit=limit)
        return jsonify(games)
    
    @app.route('/api/tournaments/<int:tournament_id>/status')
    def api_tournament_status(tournament_id):
        """API endpoint for tournament status."""
        tournament = Tournament.query.get_or_404(tournament_id)
        
        # Also get job information
        job = TournamentJob.query.filter_by(tournament_id=tournament_id).first()
        
        response = {
            'id': tournament.id,
            'name': tournament.name,
            'status': tournament.status,
            'progress': tournament.progress,
            'total_games': tournament.total_games,
            'completed_games': tournament.completed_games
        }
        
        if job:
            response['job'] = {
                'id': job.id,
                'status': job.status,
                'worker_id': job.worker_id,
                'retry_count': job.retry_count,
                'error_message': job.error_message,
                'created_at': job.created_at.isoformat() if job.created_at else None,
                'started_at': job.started_at.isoformat() if job.started_at else None,
                'last_heartbeat': job.last_heartbeat.isoformat() if job.last_heartbeat else None
            }
        
        return jsonify(response)
    
    @app.route('/api/system/health')
    def api_system_health():
        """API endpoint for system health status."""
        return jsonify(health_monitor.get_health_status())
    
    @app.route('/api/system/recovery-status')
    def api_recovery_status():
        """API endpoint for recovery status."""
        return jsonify(recovery.get_recovery_status())
    
    @app.route('/api/jobs/queue')
    def api_job_queue():
        """API endpoint for job queue status."""
        return jsonify(job_manager.get_queue_status())
    
    @app.route('/api/workers')
    def api_workers():
        """API endpoint for worker information."""
        workers = WorkerProcess.query.all()
        return jsonify([worker.to_dict() for worker in workers])
    
    @app.route('/api/jobs')
    def api_jobs():
        """API endpoint for job information."""
        limit = request.args.get('limit', 50, type=int)
        jobs = (TournamentJob.query
                .order_by(TournamentJob.created_at.desc())
                .limit(limit)
                .all())
        return jsonify([job.to_dict() for job in jobs])
    
    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)