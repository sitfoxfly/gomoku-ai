"""
Utility for parsing Python files to extract agent class information.
"""
import ast
import re
from typing import Optional, Dict, List, Tuple


class AgentParser:
    """Parser for extracting agent class information from Python files."""
    
    @staticmethod
    def parse_agent_file(file_content: str) -> Dict[str, Optional[str]]:
        """
        Parse a Python file to extract agent class information.
        
        Args:
            file_content: The content of the Python file as a string
            
        Returns:
            Dictionary containing:
            - agent_class: Name of the agent class
            - agent_name: Suggested name for the agent
            - description: Class docstring if available
            - imports: List of imports found
            - error: Error message if parsing failed
        """
        result = {
            'agent_class': None,
            'agent_name': None,
            'description': None,
            'imports': [],
            'error': None
        }
        
        try:
            # Parse the Python code into an AST
            tree = ast.parse(file_content)
            
            # Find all imports
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    for alias in node.names:
                        imports.append(f"{module}.{alias.name}")
            
            result['imports'] = imports
            
            # Find classes that inherit from Agent
            agent_classes = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Check if class inherits from Agent
                    inherits_from_agent = False
                    for base in node.bases:
                        if isinstance(base, ast.Name) and base.id == 'Agent':
                            inherits_from_agent = True
                            break
                        elif isinstance(base, ast.Attribute):
                            # Handle cases like gomoku.agents.base.Agent
                            attr_name = AgentParser._get_full_attribute_name(base)
                            if 'Agent' in attr_name:
                                inherits_from_agent = True
                                break
                    
                    if inherits_from_agent:
                        class_info = {
                            'name': node.name,
                            'docstring': ast.get_docstring(node),
                            'line_number': node.lineno
                        }
                        agent_classes.append(class_info)
            
            if agent_classes:
                # Use the first agent class found
                primary_class = agent_classes[0]
                result['agent_class'] = primary_class['name']
                result['description'] = primary_class['docstring']
                
                # Generate a suggested agent name from class name
                result['agent_name'] = AgentParser._generate_agent_name(primary_class['name'])
            else:
                result['error'] = 'No class inheriting from Agent found'
                
        except SyntaxError as e:
            result['error'] = f'Syntax error in Python file: {str(e)}'
        except Exception as e:
            result['error'] = f'Error parsing file: {str(e)}'
        
        return result
    
    @staticmethod
    def _get_full_attribute_name(node) -> str:
        """Extract the full attribute name from an AST Attribute node."""
        parts = []
        current = node
        
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        
        if isinstance(current, ast.Name):
            parts.append(current.id)
        
        return '.'.join(reversed(parts))
    
    @staticmethod
    def _generate_agent_name(class_name: str) -> str:
        """
        Generate a user-friendly agent name from a class name.
        
        Examples:
            MyGomokuAgent -> MyGomokuAgent
            SimpleAgent -> SimpleAgent  
            GomokuAI -> GomokuAI
            my_agent -> MyAgent
        """
        # Convert snake_case to PascalCase
        if '_' in class_name:
            parts = class_name.split('_')
            class_name = ''.join(word.capitalize() for word in parts)
        
        # Remove common suffixes for the display name but keep the class name intact
        # This is just for display purposes, the actual class name is preserved
        return class_name
    
    @staticmethod
    def extract_get_move_method(file_content: str) -> Optional[str]:
        """
        Extract the get_move method implementation for validation.
        
        Returns:
            The get_move method code if found, None otherwise
        """
        try:
            tree = ast.parse(file_content)
            
            for node in ast.walk(tree):
                if ((isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef)) and 
                    node.name == 'get_move'):
                    
                    # Extract the method source code
                    lines = file_content.split('\n')
                    start_line = node.lineno - 1
                    end_line = node.end_lineno if hasattr(node, 'end_lineno') else start_line + 10
                    
                    method_lines = lines[start_line:end_line]
                    return '\n'.join(method_lines)
                    
        except Exception:
            pass
        
        return None
    
    @staticmethod
    def validate_agent_structure(file_content: str) -> Tuple[bool, str]:
        """
        Validate that the Python file has proper agent structure.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            tree = ast.parse(file_content)
            
            # Check for Agent class inheritance
            has_agent_class = False
            has_get_move_method = False
            agent_class_name = None
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Check if class inherits from Agent
                    for base in node.bases:
                        if (isinstance(base, ast.Name) and base.id == 'Agent') or \
                           (isinstance(base, ast.Attribute) and 'Agent' in AgentParser._get_full_attribute_name(base)):
                            has_agent_class = True
                            agent_class_name = node.name
                            
                            # Check for get_move method in this class (both sync and async)
                            for class_node in node.body:
                                if ((isinstance(class_node, ast.FunctionDef) or isinstance(class_node, ast.AsyncFunctionDef)) and 
                                    class_node.name == 'get_move'):
                                    has_get_move_method = True
                                    break
                            break
            
            if not has_agent_class:
                return False, "No class inheriting from Agent found"
            
            if not has_get_move_method:
                return False, f"Class '{agent_class_name}' is missing the required 'get_move' method"
            
            return True, "Agent structure is valid"
            
        except SyntaxError as e:
            return False, f"Syntax error: {str(e)}"
        except Exception as e:
            return False, f"Error validating structure: {str(e)}"