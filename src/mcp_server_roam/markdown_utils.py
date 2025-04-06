from typing import List, Dict, Any, Optional, Union

class MarkdownNode:
    """Represents a node in the markdown hierarchy."""
    def __init__(self, content: str, level: int = 0):
        self.content = content
        self.level = level
        self.children: List[MarkdownNode] = []

def convert_to_roam_actions(
    nodes: List[MarkdownNode], 
    parent_uid: str, 
    order: Union[str, int] = "last"
) -> List[Dict[str, Any]]:
    """Convert markdown nodes to Roam API batch actions."""
    actions = []
    
    # Helper function to generate a random Roam UID
    def generate_uid() -> str:
        import random
        import string
        chars = string.ascii_letters + string.digits + "-_"
        return ''.join(random.choice(chars) for _ in range(9))
    
    # Helper function to recursively create actions
    def create_block_actions(nodes: List[MarkdownNode], parent_uid: str, order: Union[str, int]) -> None:
        for node in nodes:
            uid = generate_uid()
            
            # Create the block
            action = {
                "action": "create-block",
                "location": {
                    "parent-uid": parent_uid,
                    "order": order
                },
                "block": {
                    "uid": uid,
                    "string": node.content
                }
            }
            
            actions.append(action)
            
            # Process children if any
            if node.children:
                create_block_actions(node.children, uid, "last")
    
    # Create all actions
    create_block_actions(nodes, parent_uid, order)
    return actions

def parse_markdown(markdown: str) -> List[MarkdownNode]:
    """Parse markdown text into a hierarchical structure of nodes."""
    lines = markdown.split('\n')
    root_nodes = []
    stack = []
    
    for line in lines:
        # Skip empty lines
        if not line.strip():
            continue
        
        # Calculate indentation level (assume 2 spaces = 1 level)
        indent = len(line) - len(line.lstrip())
        level = indent // 2
        
        # Handle bullet points
        content = line.strip()
        if content.startswith(('- ', '* ', '+ ')):
            content = content[2:]
        
        # Create node
        node = MarkdownNode(content, level)
        
        # Add to appropriate parent
        while stack and stack[-1].level >= level:
            stack.pop()
        
        if not stack:
            root_nodes.append(node)
        else:
            stack[-1].children.append(node)
        
        stack.append(node)
    
    return root_nodes

def convert_to_roam_markdown(text: str) -> str:
    """Convert standard markdown to Roam-flavored markdown."""
    # Handle bold
    text = text.replace("**", "**")  # Keep double asterisks
    
    # Handle italic
    text = text.replace("*", "__")  # Single asterisk to double underscore
    
    # Handle tasks
    text = text.replace("- [ ]", "- {{[[TODO]]}}")
    text = text.replace("- [x]", "- {{[[DONE]]}}")
    
    return text
