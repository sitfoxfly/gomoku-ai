"""Dynamic agent loading system for student submissions."""

import json
import importlib.util
import importlib
import inspect
import os
import tempfile
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Type, Union
import git
from ..agents.base import Agent


class AgentValidationError(Exception):
    """Raised when an agent fails validation."""

    pass


@dataclass
class AgentMetadata:
    """Metadata for a discovered agent."""

    name: str  # Unique identifier (e.g., "student1.MinimaxAgent")
    display_name: str  # From manifest "name" field
    agent_class: str  # Package notation (e.g., "minimax_agent.MinimaxGomokuAgent")
    manifest_path: str
    source_type: str  # 'local' or 'github'
    source_path: str
    author: List[str] = field(default_factory=list)
    description: Optional[str] = None
    version: Optional[str] = None
    validated: bool = False
    validation_error: Optional[str] = None
    loaded_class: Optional[Type] = None


class AgentLoader:
    """Dynamic agent loader for local folders and GitHub repositories."""

    def __init__(self, temp_dir: Optional[str] = None, include_builtin: bool = True):
        self.temp_dir = temp_dir or tempfile.mkdtemp(prefix="gomoku_agents_")
        self.discovered_agents: Dict[str, AgentMetadata] = {}
        self.loaded_classes: Dict[str, Type[Agent]] = {}

        if include_builtin:
            self._discover_builtin_agents()

    def _discover_builtin_agents(self):
        """Discover built-in agents from gomoku.agents module."""
        try:
            # Import the agents module
            import gomoku.agents as agents_module

            # Get all classes from the module
            for name, obj in inspect.getmembers(agents_module, inspect.isclass):
                # Skip the base Agent class and non-Agent classes
                if obj is not Agent and issubclass(obj, Agent) and obj.__module__.startswith("gomoku.agents"):

                    # Create metadata for built-in agent using agent_class as name
                    agent_class_name = f"{obj.__module__}.{obj.__name__}"
                    metadata = AgentMetadata(
                        name=agent_class_name,
                        display_name=name,
                        agent_class=agent_class_name,
                        manifest_path="<builtin>",
                        source_type="builtin",
                        source_path="gomoku.agents",
                        author=["Gomoku Framework"],
                        description=f"Built-in {name} agent",
                        version="1.0.0",
                    )

                    # Mark as validated and cache the class
                    metadata.validated = True
                    metadata.loaded_class = obj

                    self.discovered_agents[agent_class_name] = metadata
                    self.loaded_classes[agent_class_name] = obj

        except Exception as e:
            print(f"Warning: Failed to discover built-in agents: {e}")

    def discover_from_directories(self, directories: List[str]) -> int:
        """Discover agents from multiple local directories."""
        total_discovered = 0

        for directory in directories:
            directory = Path(directory).resolve()
            if not directory.exists():
                print(f"Warning: Directory not found: {directory}")
                continue

            # Recursively find all agent.json files
            for manifest_path in directory.rglob("agent.json"):
                try:
                    metadata = self._parse_manifest(manifest_path, "local", str(directory))
                    if metadata:
                        self.discovered_agents[metadata.name] = metadata
                        total_discovered += 1
                except Exception as e:
                    print(f"Warning: Failed to parse manifest {manifest_path}: {e}")

        return total_discovered

    def discover_from_github_repos(self, repo_urls: List[str], branch: str = "main") -> int:
        """Discover agents from multiple GitHub repositories."""
        total_discovered = 0

        for repo_url in repo_urls:
            try:
                repo_name = repo_url.split("/")[-1].replace(".git", "")
                clone_path = Path(self.temp_dir) / repo_name

                # Clean up existing clone
                if clone_path.exists():
                    shutil.rmtree(clone_path)

                # Clone repository
                git.Repo.clone_from(repo_url, clone_path, branch=branch, depth=1)

                # Find agent.json files in cloned repo
                for manifest_path in clone_path.rglob("agent.json"):
                    try:
                        metadata = self._parse_manifest(manifest_path, "github", repo_url)
                        if metadata:
                            self.discovered_agents[metadata.name] = metadata
                            total_discovered += 1
                    except Exception as e:
                        print(f"Warning: Failed to parse manifest {manifest_path}: {e}")

            except Exception as e:
                print(f"Warning: Failed to clone repository {repo_url}: {e}")

        return total_discovered

    def _parse_manifest(self, manifest_path: Path, source_type: str, source_path: str) -> Optional[AgentMetadata]:
        """Parse an agent.json manifest file."""
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)

            # Validate required fields
            required_fields = ["name", "agent_class"]
            for field in required_fields:
                if field not in manifest:
                    raise ValueError(f"Missing required field: {field}")

            # Create unique agent name using folder structure and Python file
            agent_dir = manifest_path.parent
            if source_type == "local":
                # Use relative path from source directory
                source_path_obj = Path(source_path)
                try:
                    relative_path = agent_dir.relative_to(source_path_obj)
                    # Filter out '.' and '..' components and 'discovery' directory
                    path_parts = [part for part in relative_path.parts if part not in (".", "..", "discovery")]

                    # Extract Python file name from agent_class
                    agent_class_parts = manifest["agent_class"].split(".")
                    if len(agent_class_parts) >= 2:
                        python_file = agent_class_parts[0]  # First part is usually the module/file name
                        path_parts.append(python_file)

                    namespace = ".".join(path_parts) if path_parts else agent_dir.name
                except ValueError:
                    # Fallback to directory name if relative path fails
                    namespace = agent_dir.name
            else:  # github
                repo_name = source_path.split("/")[-1].replace(".git", "")
                if agent_dir.name != repo_name:
                    namespace = f"{repo_name}.{agent_dir.name}"
                else:
                    namespace = repo_name

            # Use agent_class as the primary name identifier
            primary_name = manifest["agent_class"]
            
            # Handle name conflicts by adding source namespace
            if primary_name in self.discovered_agents:
                # Add namespace to resolve conflicts
                unique_name = f"{namespace}.{primary_name}"
                
                # If still conflicted, add counter
                if unique_name in self.discovered_agents:
                    counter = 1
                    while f"{unique_name}_{counter}" in self.discovered_agents:
                        counter += 1
                    unique_name = f"{unique_name}_{counter}"
            else:
                unique_name = primary_name

            return AgentMetadata(
                name=unique_name,
                display_name=manifest["name"],
                agent_class=manifest["agent_class"],
                manifest_path=str(manifest_path),
                source_type=source_type,
                source_path=source_path,
                author=self._parse_authors(manifest.get("author")),
                description=manifest.get("description"),
                version=manifest.get("version"),
            )

        except Exception as e:
            print(f"Error parsing manifest {manifest_path}: {e}")
            return None

    def _parse_authors(self, author_data) -> List[str]:
        """Parse author field from manifest, supporting both string and list formats."""
        if author_data is None:
            return []
        elif isinstance(author_data, str):
            # Split by comma if multiple authors in string format
            return [author.strip() for author in author_data.split(",") if author.strip()]
        elif isinstance(author_data, list):
            # Already a list, just clean up strings
            return [str(author).strip() for author in author_data if str(author).strip()]
        else:
            # Fallback: convert to string
            return [str(author_data).strip()] if str(author_data).strip() else []

    def validate_agent(self, agent_name: str) -> bool:
        """Validate that an agent properly implements the Agent interface."""
        if agent_name not in self.discovered_agents:
            raise ValueError(f"Agent {agent_name} not found in discovered agents")

        metadata = self.discovered_agents[agent_name]

        try:
            # Load the agent class
            agent_class = self._load_agent_class(metadata)

            # Check that it's a subclass of Agent
            if not issubclass(agent_class, Agent):
                raise AgentValidationError(f"{metadata.agent_class} is not a subclass of Agent")

            # Check that required methods are implemented
            if not hasattr(agent_class, "get_move"):
                raise AgentValidationError(f"{metadata.agent_class} does not implement get_move method")

            # Try to instantiate (basic smoke test)
            try:
                test_agent = agent_class("test_agent")
                if not hasattr(test_agent, "agent_id"):
                    raise AgentValidationError(f"{metadata.agent_class} missing agent_id attribute")
            except Exception as e:
                raise AgentValidationError(f"Failed to instantiate {metadata.agent_class}: {e}")

            metadata.validated = True
            metadata.validation_error = None
            metadata.loaded_class = agent_class
            return True

        except Exception as e:
            metadata.validated = False
            metadata.validation_error = str(e)
            return False

    def _load_agent_class(self, metadata: AgentMetadata) -> Type[Agent]:
        """Load an agent class from its metadata."""
        manifest_path = Path(metadata.manifest_path)
        agent_dir = manifest_path.parent

        # Add agent directory to Python path temporarily
        agent_dir_str = str(agent_dir)
        if agent_dir_str not in sys.path:
            sys.path.insert(0, agent_dir_str)

        try:
            # Parse the agent_class string (e.g., "minimax_agent.MinimaxGomokuAgent")
            parts = metadata.agent_class.split(".")
            if len(parts) < 2:
                raise ValueError(f"Invalid agent_class format: {metadata.agent_class}. Expected 'module.ClassName'")

            module_name = ".".join(parts[:-1])
            class_name = parts[-1]

            # Import the module
            module_path = agent_dir / f"{module_name.replace('.', os.sep)}.py"
            if not module_path.exists():
                raise FileNotFoundError(f"Module file not found: {module_path}")

            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                raise RuntimeError(f"Could not create module spec for {module_path}")

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Get the agent class
            if not hasattr(module, class_name):
                raise RuntimeError(f"Class {class_name} not found in {module_path}")

            agent_class = getattr(module, class_name)

            # Cache the loaded class
            self.loaded_classes[metadata.name] = agent_class

            return agent_class

        finally:
            # Clean up sys.path
            if agent_dir_str in sys.path:
                sys.path.remove(agent_dir_str)

    def get_agent(self, agent_name: str, instance_id: Optional[str] = None) -> Agent:
        """Load and instantiate an agent by name."""
        if agent_name not in self.discovered_agents:
            raise ValueError(f"Agent {agent_name} not found. Available agents: {list(self.discovered_agents.keys())}")

        metadata = self.discovered_agents[agent_name]

        # Validate if not already validated
        if not metadata.validated:
            if not self.validate_agent(agent_name):
                raise AgentValidationError(f"Agent validation failed: {metadata.validation_error}")

        # Use cached class if available
        if metadata.loaded_class:
            agent_class = metadata.loaded_class
        elif agent_name in self.loaded_classes:
            agent_class = self.loaded_classes[agent_name]
        else:
            agent_class = self._load_agent_class(metadata)

        # Create instance
        instance_id = instance_id or metadata.display_name
        return agent_class(instance_id)

    def list_agents(self, validated_only: bool = False) -> List[AgentMetadata]:
        """List all discovered agents."""
        agents = list(self.discovered_agents.values())
        if validated_only:
            agents = [a for a in agents if a.validated]
        return agents

    def list_validated_agents(self) -> List[str]:
        """Get list of validated agent names for easy tournament use."""
        return [name for name, metadata in self.discovered_agents.items() if metadata.validated]

    def validate_all_agents(self) -> Dict[str, bool]:
        """Validate all discovered agents and return results."""
        results = {}
        for agent_name in self.discovered_agents:
            results[agent_name] = self.validate_agent(agent_name)
        return results

    def get_agent_info(self, agent_name: str) -> Optional[AgentMetadata]:
        """Get metadata for a specific agent."""
        return self.discovered_agents.get(agent_name)

    def cleanup(self):
        """Clean up temporary directories."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def __del__(self):
        """Cleanup when object is destroyed."""
        try:
            self.cleanup()
        except:
            pass  # Ignore cleanup errors during destruction
