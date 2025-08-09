"""Agent validation system for uploaded agents."""

import ast
import json
from pathlib import Path
from typing import Dict, Optional, Tuple, Any

from ..agents.base import Agent
from ..core.models import Player, GameState


class AgentValidator:
    """Validates uploaded agents for security and functionality."""

    # Dangerous imports/functions to check for
    _DANGEROUS_IMPORTS = {
        'os', 'subprocess', 'sys', 'importlib', 'eval', 'exec',
        'open', '__import__', 'globals', 'locals',
        'vars', 'dir', 'getattr', 'setattr', 'delattr',
        'socket', 'urllib', 'requests', 'http'
    }

    # Dangerous direct function calls
    _DANGEROUS_FUNCTIONS = {
        '__import__', 'exec', 'eval', 'compile', 'open', 'file',
        'input', 'raw_input'
    }

    # Dangerous module operations
    _DANGEROUS_OPERATIONS = {
        'os': ['remove', 'unlink', 'rmdir', 'system', 'popen', 'open'],
        'shutil': ['rmtree', 'move', 'copy'],
        'pathlib': ['unlink', 'rmdir'],
        'subprocess': ['call', 'run', 'Popen', 'check_call', 'check_output']
    }

    # Required files for a valid agent
    _REQUIRED_FILES = ['agent.json']

    def __init__(self, upload_dir: str = "uploads"):
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(exist_ok=True)

    def validate_agent(self, agent_dir: str) -> Tuple[bool, Optional[str]]:
        """
        Validate an uploaded agent directory.
        Returns (is_valid, error_message)
        """
        try:
            agent_path = Path(agent_dir)

            # Check required files exist
            validation_error = self._check_required_files(agent_path)
            if validation_error:
                return False, validation_error

            # Validate agent.json
            validation_error = self._validate_agent_json(agent_path / 'agent.json')
            if validation_error:
                return False, validation_error

            # Validate Python code - get filename from manifest
            try:
                with open(agent_path / 'agent.json', 'r') as f:
                    manifest = json.load(f)

                python_filename = manifest.get('python_file', 'agent.py')  # fallback for backward compatibility
                validation_error = self._validate_python_code(agent_path / python_filename)
                if validation_error:
                    return False, validation_error
            except (json.JSONDecodeError, FileNotFoundError) as e:
                return False, f"Error reading agent.json for Python validation: {str(e)}"

            # Test agent loading and basic functionality
            validation_error = self._test_agent_functionality(agent_dir)
            if validation_error:
                return False, validation_error

            return True, None

        except Exception as e:
            return False, f"Validation failed: {str(e)}"

    def _check_required_files(self, agent_path: Path) -> Optional[str]:
        """Check that all required files are present."""
        for required_file in self._REQUIRED_FILES:
            file_path = agent_path / required_file
            if not file_path.exists():
                return f"Missing required file: {required_file}"

            if not file_path.is_file():
                return f"Required path is not a file: {required_file}"

        # Check for Python file specified in agent.json
        try:
            with open(agent_path / 'agent.json', 'r') as f:
                manifest = json.load(f)

            python_file = manifest.get('python_file')
            if python_file:
                python_path = agent_path / python_file
                if not python_path.exists():
                    return f"Missing Python file specified in manifest: {python_file}"
                if not python_path.is_file():
                    return f"Python file path is not a file: {python_file}"
            else:
                # For backward compatibility, check for agent.py
                if (agent_path / 'agent.py').exists():
                    pass  # agent.py exists, that's fine
                else:
                    return "No Python file specified in manifest and agent.py not found"
        except (json.JSONDecodeError, FileNotFoundError):
            return "Cannot read agent.json to verify Python file"

        return None

    def _validate_agent_json(self, json_path: Path) -> Optional[str]:
        """Validate the agent.json manifest file."""
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)

            # Check required fields
            required_fields = ['name', 'agent_class', 'author']
            for field in required_fields:
                if field not in data:
                    return f"Missing required field in agent.json: {field}"

                if not isinstance(data[field], str) or not data[field].strip():
                    return f"Invalid value for {field} in agent.json"

            # Validate agent_class format
            agent_class = data['agent_class']
            if '.' not in agent_class:
                return "agent_class must be in format 'module.ClassName'"

            return None

        except json.JSONDecodeError as e:
            return f"Invalid JSON in agent.json: {str(e)}"
        except Exception as e:
            return f"Error reading agent.json: {str(e)}"

    def _validate_python_code(self, python_path: Path) -> Optional[str]:
        """Validate Python code for syntax and security issues."""
        try:
            with open(python_path, 'r') as f:
                code = f.read()

            # Parse AST to check syntax
            try:
                tree = ast.parse(code)
            except SyntaxError as e:
                return f"Syntax error in agent.py: {str(e)}"

            # Security checks
            security_error = self._check_security_issues(tree)
            if security_error:
                return security_error

            return None

        except Exception as e:
            return f"Error validating Python code: {str(e)}"

    def _check_security_issues(self, tree: ast.AST) -> Optional[str]:
        """Check for potentially dangerous code patterns using AST analysis."""

        for node in ast.walk(tree):
            # Check imports
            if isinstance(node, ast.Import):
                error = self._check_import_node(node)
                if error:
                    return error

            elif isinstance(node, ast.ImportFrom):
                error = self._check_import_from_node(node)
                if error:
                    return error

            # Check function calls
            elif isinstance(node, ast.Call):
                error = self._check_function_call_node(node)
                if error:
                    return error

        return None

    def _check_import_node(self, node: ast.Import) -> Optional[str]:
        """Check ast.Import nodes for dangerous imports."""
        for alias in node.names:
            if alias.name in self._DANGEROUS_IMPORTS:
                return f"Dangerous import detected: {alias.name}"
        return None

    def _check_import_from_node(self, node: ast.ImportFrom) -> Optional[str]:
        """Check ast.ImportFrom nodes for dangerous imports."""
        if node.module and node.module in self._DANGEROUS_IMPORTS:
            return f"Dangerous import detected: {node.module}"

        for alias in node.names:
            if alias.name in self._DANGEROUS_IMPORTS:
                return f"Dangerous import detected: {alias.name}"
        return None

    def _check_function_call_node(self, node: ast.Call) -> Optional[str]:
        """Check ast.Call nodes for dangerous function calls."""
        # Direct function calls (e.g., exec(), eval())
        if isinstance(node.func, ast.Name):
            return self._check_direct_function_call(node.func.id)

        # Attribute access calls (e.g., os.system(), Path.unlink())
        elif isinstance(node.func, ast.Attribute):
            return self._check_attribute_function_call(node.func)

        return None

    def _check_direct_function_call(self, func_name: str) -> Optional[str]:
        """Check direct function calls for dangerous patterns."""
        if func_name in self._DANGEROUS_FUNCTIONS:
            return f"Dangerous function call: {func_name}"

        return None

    def _check_attribute_function_call(self, func_node: ast.Attribute) -> Optional[str]:
        """Check attribute-based function calls for dangerous patterns."""
        # Handle module.function patterns (e.g., os.remove, shutil.rmtree)
        if isinstance(func_node.value, ast.Name):
            module_name = func_node.value.id
            func_name = func_node.attr

            if module_name in self._DANGEROUS_OPERATIONS:
                if func_name in self._DANGEROUS_OPERATIONS[module_name]:
                    return f"Dangerous operation detected: {module_name}.{func_name}"

        # Handle chained attribute access (e.g., Path(...).unlink())
        elif isinstance(func_node.value, ast.Attribute):
            if func_node.attr in ['unlink', 'rmdir']:
                return f"Dangerous file operation detected: .{func_node.attr}()"

        # Handle method calls on objects that might be dangerous
        # This catches patterns like: path_obj.unlink() where path_obj could be a Path
        elif func_node.attr in ['unlink', 'rmdir', 'remove']:
            return f"Potentially dangerous file operation: .{func_node.attr}()"

        return None

    def _test_agent_functionality(self, agent_dir: str, board_size: int = 8) -> Optional[str]:
        """Test that the agent can be loaded and make basic moves."""
        try:
            # Load the agent directly without using the global discovery system
            agent_path = Path(agent_dir)

            # Read the agent.json to get the agent class
            with open(agent_path / 'agent.json', 'r') as f:
                manifest = json.load(f)

            agent_class_name = manifest['agent_class']
            if '.' not in agent_class_name:
                return "agent_class must be in format 'module.ClassName'"

            module_name, class_name = agent_class_name.rsplit('.', 1)

            # Import the agent module directly
            import importlib.util
            import sys

            module_path = agent_path / f"{module_name}.py"
            if not module_path.exists():
                return f"Agent module file not found: {module_name}.py"

            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                return f"Could not load module spec for {module_name}"

            module = importlib.util.module_from_spec(spec)

            # Add the agent directory to sys.path temporarily so imports work
            original_path = sys.path.copy()
            sys.path.insert(0, str(agent_path))

            try:
                spec.loader.exec_module(module)

                # Get the agent class
                if not hasattr(module, class_name):
                    return f"Agent class '{class_name}' not found in module"

                agent_class = getattr(module, class_name)

                # Check that it inherits from Agent
                if not issubclass(agent_class, Agent):
                    return f"Class '{class_name}' does not inherit from Agent base class"

                # Instantiate the agent with a test ID
                agent = agent_class("test_agent")
                agent.player = Player.BLACK

                # Test that it can make a move on an empty board
                empty_board = [[Player.EMPTY.value for _ in range(board_size)] for _ in range(board_size)]
                game_state = GameState(
                    board=empty_board,
                    current_player=Player.BLACK,
                    move_history=[],
                    board_size=board_size
                )

                # Run the agent's get_move method with a timeout
                import asyncio

                async def test_move():
                    timeout_seconds = 20.0
                    try:
                        move = await asyncio.wait_for(
                            agent.get_move(game_state),
                            timeout=timeout_seconds
                        )
                        return move
                    except asyncio.TimeoutError:
                        raise Exception(f"Agent took too long to make a move (>{timeout_seconds} seconds)")

                # Run the async test
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    move = loop.run_until_complete(test_move())
                finally:
                    loop.close()

                # Validate the move format
                if not isinstance(move, tuple) or len(move) != 2:
                    return "Agent returned invalid move format (must be (row, col) tuple)"

                row, col = move
                if not isinstance(row, int) or not isinstance(col, int):
                    return "Agent returned non-integer coordinates"

                if not (0 <= row < board_size) or not (0 <= col < board_size):
                    return f"Agent returned invalid coordinates: ({row}, {col}) for board size {board_size}x{board_size}"

                return None

            finally:
                # Restore original sys.path
                sys.path[:] = original_path

        except Exception as e:
            return f"Functionality test failed: {str(e)}"

    def save_uploaded_files(self, files: Dict[str, Any], metadata: Dict[str, str]) -> Tuple[bool, str]:
        """
        Save uploaded files to disk and return the agent directory path.
        Returns (success, path_or_error)
        """
        try:
            # Create unique directory for this agent
            import uuid
            import hashlib
            agent_id = str(uuid.uuid4())[:8]
            agent_name = metadata.get('name', 'unknown').replace(' ', '_').lower()
            agent_dir = self.upload_dir / f"{agent_name}_{agent_id}"
            agent_dir.mkdir(exist_ok=True)

            # Generate hash-based filename for the Python file
            if 'agent_file' in files:
                agent_file = files['agent_file']
                file_content = agent_file.read()
                agent_file.seek(0)  # Reset file pointer for saving

                # Create salt from timestamp, author, and agent name for better uniqueness
                import time
                timestamp = str(int(time.time() * 1000))  # millisecond precision
                author = metadata.get('author', '').strip()
                name = metadata.get('name', '').strip()
                salt = f"{timestamp}:{author}:{name}"

                # Combine file content with salt for hash
                salted_content = file_content + salt.encode('utf-8')
                file_hash = hashlib.sha256(salted_content).hexdigest()[:20]
                python_filename = f"{file_hash}.py"
            else:
                return False, "No agent file provided"

            # Save agent.json with hash-based module reference
            agent_json = {
                'name': metadata.get('name', ''),
                'author': metadata.get('author', ''),
                'description': metadata.get('description', ''),
                'version': metadata.get('version', '1.0.0'),
                'agent_class': f'{file_hash}.{metadata.get("class_name", "Agent")}',
                'python_file': python_filename
            }

            with open(agent_dir / 'agent.json', 'w') as f:
                json.dump(agent_json, f, indent=2)

            # Save uploaded Python file with hash-based name
            agent_file.save(agent_dir / python_filename)

            return True, str(agent_dir)

        except Exception as e:
            return False, f"Failed to save files: {str(e)}"