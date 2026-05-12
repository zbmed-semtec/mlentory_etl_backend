import os
import glob
import re
from typing import List, Dict, Any, Optional, Tuple

class PlatformDocsController:
    """
    Controller for managing and retrieving platform-specific documentation.
    
    This controller handles loading, processing, and retrieving relevant sections
    from platform documentation files to enhance LLM responses with accurate
    platform-specific information.
    
    Args:
        docs_base_path: Base path to the platform documentation files
    
    Returns:
        PlatformDocsController instance
    
    Raises:
        FileNotFoundError: If the docs_base_path doesn't exist
    """
    
    def __init__(self, docs_base_path: str = "data/platform_docs"):
        """Initialize the platform docs controller with the path to documentation files."""
        self.docs_base_path = docs_base_path
        self.platforms = {}
        self.load_all_platforms()
    
    def load_all_platforms(self) -> None:
        """
        Load all available platform documentation.
        
        Scans the docs_base_path for platform directories and loads their documentation.
        
        Args:
            None
            
        Returns:
            None
            
        Raises:
            FileNotFoundError: If the docs_base_path doesn't exist
        """
        if not os.path.exists(self.docs_base_path):
            raise FileNotFoundError(f"Documentation path not found: {self.docs_base_path}")
            
        # Get all platform directories
        platform_dirs = [d for d in os.listdir(self.docs_base_path) 
                        if os.path.isdir(os.path.join(self.docs_base_path, d))]
        
        for platform in platform_dirs:
            self.load_platform(platform)
    
    def load_platform(self, platform_name: str) -> None:
        """
        Load documentation for a specific platform.
        
        Args:
            platform_name: Name of the platform to load
            
        Returns:
            None
            
        Raises:
            FileNotFoundError: If the platform directory doesn't exist
        """
        platform_path = os.path.join(self.docs_base_path, platform_name)
        
        if not os.path.exists(platform_path):
            raise FileNotFoundError(f"Platform documentation not found: {platform_path}")
        
        # Find all markdown files in the platform directory
        doc_files = glob.glob(os.path.join(platform_path, "*.md"))
        
        platform_docs = {}
        
        for doc_file in doc_files:
            doc_name = os.path.basename(doc_file).replace(".md", "")
            with open(doc_file, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Parse the document into sections
            sections = self._parse_document_sections(content)
            platform_docs[doc_name] = {
                "path": doc_file,
                "content": content,
                "sections": sections
            }
        
        self.platforms[platform_name] = platform_docs
    
    def _parse_document_sections(self, content: str) -> Dict[str, str]:
        """
        Parse a markdown document into sections based on headings.
        
        Args:
            content: Markdown content to parse
            
        Returns:
            Dict mapping section titles to their content
        
        Example:
            For a document with "## Section 1" and "## Section 2", returns
            {"Section 1": "content...", "Section 2": "content..."}
        """
        # Split by heading markers (##, ###, etc.)
        section_pattern = r'^(#{2,4})\s+(.+)$'
        lines = content.split('\n')
        
        sections = {}
        current_section = None
        current_content = []
        
        for line in lines:
            match = re.match(section_pattern, line)
            if match:
                # Save the previous section if it exists
                if current_section:
                    sections[current_section] = '\n'.join(current_content)
                
                # Start a new section
                current_section = match.group(2).strip()
                current_content = []
            elif current_section:
                current_content.append(line)
        
        # Save the last section
        if current_section:
            sections[current_section] = '\n'.join(current_content)
        
        return sections
    
    def get_available_platforms(self) -> List[str]:
        """
        Get a list of available platforms.
        
        Args:
            None
            
        Returns:
            List of platform names
            
        Example:
            ["huggingface", "tensorflow", "pytorch"]
        """
        return list(self.platforms.keys())
    
    def get_platform_docs(self, platform_name: str) -> List[str]:
        """
        Get a list of available documentation files for a platform.
        
        Args:
            platform_name: Name of the platform
            
        Returns:
            List of documentation file names
            
        Raises:
            KeyError: If the platform doesn't exist
            
        Example:
            ["platform_overview", "transformers_library_guide"]
        """
        if platform_name not in self.platforms:
            raise KeyError(f"Platform not found: {platform_name}")
        
        return list(self.platforms[platform_name].keys())
    
    def get_doc_content(self, platform_name: str, doc_name: str) -> str:
        """
        Get the full content of a specific documentation file.
        
        Args:
            platform_name: Name of the platform
            doc_name: Name of the documentation file
            
        Returns:
            Full content of the documentation file
            
        Raises:
            KeyError: If the platform or document doesn't exist
        """
        if platform_name not in self.platforms:
            raise KeyError(f"Platform not found: {platform_name}")
        
        if doc_name not in self.platforms[platform_name]:
            raise KeyError(f"Documentation not found: {doc_name}")
        
        return self.platforms[platform_name][doc_name]["content"]
    
    def get_doc_sections(self, platform_name: str, doc_name: str) -> List[str]:
        """
        Get a list of sections in a specific documentation file.
        
        Args:
            platform_name: Name of the platform
            doc_name: Name of the documentation file
            
        Returns:
            List of section titles
            
        Raises:
            KeyError: If the platform or document doesn't exist
        """
        if platform_name not in self.platforms:
            raise KeyError(f"Platform not found: {platform_name}")
        
        if doc_name not in self.platforms[platform_name]:
            raise KeyError(f"Documentation not found: {doc_name}")
        
        return list(self.platforms[platform_name][doc_name]["sections"].keys())
    
    def get_section_content(self, platform_name: str, doc_name: str, section_title: str) -> str:
        """
        Get the content of a specific section in a documentation file.
        
        Args:
            platform_name: Name of the platform
            doc_name: Name of the documentation file
            section_title: Title of the section
            
        Returns:
            Content of the section
            
        Raises:
            KeyError: If the platform, document, or section doesn't exist
        """
        if platform_name not in self.platforms:
            raise KeyError(f"Platform not found: {platform_name}")
        
        if doc_name not in self.platforms[platform_name]:
            raise KeyError(f"Documentation not found: {doc_name}")
        
        sections = self.platforms[platform_name][doc_name]["sections"]
        if section_title not in sections:
            raise KeyError(f"Section not found: {section_title}")
        
        return sections[section_title]
    
    def search_platform_docs(self, platform_name: str, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Search for relevant content in platform documentation.
        
        Performs a simple keyword search across all documentation files for a platform.
        
        Args:
            platform_name: Name of the platform
            query: Search query
            max_results: Maximum number of results to return
            
        Returns:
            List of dictionaries containing doc_name, section_title, and content
            
        Raises:
            KeyError: If the platform doesn't exist
            
        Example:
            [
                {
                    "doc_name": "transformers_library_guide",
                    "section_title": "Text Generation",
                    "content": "..."
                },
                ...
            ]
        """
        if platform_name not in self.platforms:
            raise KeyError(f"Platform not found: {platform_name}")
        
        results = []
        query_terms = query.lower().split()
        
        for doc_name, doc_data in self.platforms[platform_name].items():
            for section_title, section_content in doc_data["sections"].items():
                # Calculate a simple relevance score based on term frequency
                score = 0
                for term in query_terms:
                    score += section_content.lower().count(term)
                
                if score > 0:
                    results.append({
                        "doc_name": doc_name,
                        "section_title": section_title,
                        "content": section_content,
                        "score": score
                    })
        
        # Sort by relevance score and limit results
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:max_results]
    
    def get_context_for_llm(self, platform_name: str, query: str, max_tokens: int = 4000) -> str:
        """
        Get formatted context from platform documentation for use with an LLM.
        
        Searches for relevant content and formats it for inclusion in an LLM prompt.
        
        Args:
            platform_name: Name of the platform
            query: Search query
            max_tokens: Maximum number of tokens to include in the context
            
        Returns:
            Formatted context string
            
        Raises:
            KeyError: If the platform doesn't exist
            
        Example:
            "## From transformers_library_guide - Text Generation\n...\n## From datasets_library_guide - Loading Datasets\n..."
        """
        if platform_name not in self.platforms:
            raise KeyError(f"Platform not found: {platform_name}")
        
        # Search for relevant content
        search_results = self.search_platform_docs(platform_name, query)
        
        # Format the results
        context_parts = []
        total_length = 0
        
        for result in search_results:
            doc_name = result["doc_name"]
            section_title = result["section_title"]
            content = result["content"]
            
            # Estimate token count (rough approximation: 4 chars = 1 token)
            content_tokens = len(content) // 4
            
            if total_length + content_tokens > max_tokens:
                # Truncate content to fit within max_tokens
                chars_to_keep = (max_tokens - total_length) * 4
                content = content[:chars_to_keep] + "..."
            
            formatted_section = f"## From {doc_name} - {section_title}\n{content}"
            context_parts.append(formatted_section)
            
            total_length += content_tokens
            if total_length >= max_tokens:
                break
        
        return "\n\n".join(context_parts)
    
    def get_multi_platform_context(self, platforms: List[str], query: str, max_tokens: int = 6000) -> str:
        """
        Get formatted context from multiple platform documentations.
        
        Args:
            platforms: List of platform names
            query: Search query
            max_tokens: Maximum number of tokens to include in the context
            
        Returns:
            Formatted context string combining relevant information from multiple platforms
            
        Raises:
            KeyError: If any platform doesn't exist
        """
        all_results = []
        
        # Allocate tokens proportionally to each platform
        tokens_per_platform = max_tokens // len(platforms)
        
        for platform in platforms:
            if platform not in self.platforms:
                raise KeyError(f"Platform not found: {platform}")
            
            # Search for relevant content
            platform_results = self.search_platform_docs(platform, query)
            
            # Add platform name to each result
            for result in platform_results:
                result["platform"] = platform
            
            all_results.extend(platform_results)
        
        # Sort all results by relevance score
        all_results.sort(key=lambda x: x["score"], reverse=True)
        
        # Format the results
        context_parts = []
        total_length = 0
        
        for result in all_results:
            platform = result["platform"]
            doc_name = result["doc_name"]
            section_title = result["section_title"]
            content = result["content"]
            
            # Estimate token count (rough approximation: 4 chars = 1 token)
            content_tokens = len(content) // 4
            
            if total_length + content_tokens > max_tokens:
                # Truncate content to fit within max_tokens
                chars_to_keep = (max_tokens - total_length) * 4
                content = content[:chars_to_keep] + "..."
            
            formatted_section = f"## From {platform}/{doc_name} - {section_title}\n{content}"
            context_parts.append(formatted_section)
            
            total_length += content_tokens
            if total_length >= max_tokens:
                break
        
        return "\n\n".join(context_parts) 