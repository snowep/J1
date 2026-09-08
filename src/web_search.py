import json
import os
import re
import requests
from typing import Dict, List, Optional


class WebSearch:
    """
    Web search utility for JARVIS to find content when knowledge is insufficient.
    Uses DuckDuckGo HTML scraping as a simple, no-API-key search method.
    """
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
    
    def search(self, query: str, max_results: int = 5) -> List[Dict]:
        """
        Search the web for information.
        
        Args:
            query: Search query
            max_results: Maximum number of results to return
            
        Returns:
            List of search results with title, url, and snippet
        """
        try:
            # Use DuckDuckGo HTML
            url = "https://html.duckduckgo.com/html/"
            params = {'q': query}
            
            response = self.session.post(url, data=params, timeout=15)
            
            if response.status_code != 200:
                return []
            
            # Parse HTML for results
            results = self._parse_ddg_results(response.text, max_results)
            return results
            
        except Exception as e:
            print(f"Web search error: {e}")
            return []
    
    def _parse_ddg_results(self, html: str, max_results: int) -> List[Dict]:
        """Parse DuckDuckGo HTML results."""
        import re
        
        results = []
        
        # Find result blocks
        # DuckDuckGo result pattern
        result_pattern = r'class="result__url">(.*?)</a>.*?class="result__snippet">(.*?)</a>'
        matches = re.findall(result_pattern, html, re.DOTALL)
        
        for i, (url_part, snippet) in enumerate(matches[:max_results]):
            # Clean up snippet
            snippet = re.sub(r'<[^>]+>', '', snippet)
            snippet = snippet.strip()
            
            # Extract URL
            url_match = re.search(r'href="([^"]+)"', url_part)
            url = url_match.group(1) if url_match else ''
            
            # Extract title from snippet or use URL
            title = snippet[:80] + "..." if len(snippet) > 80 else snippet
            
            results.append({
                'title': title,
                'url': url,
                'snippet': snippet[:300]
            })
        
        # Alternative pattern if first didn't work
        if not results:
            alt_pattern = r'class="result__title">.*?href="([^"]+)".*?>([^<]+)</a>.*?class="result__snippet">([^<]+)'
            alt_matches = re.findall(alt_pattern, html, re.DOTALL)
            
            for url, title, snippet in alt_matches[:max_results]:
                results.append({
                    'title': title.strip(),
                    'url': url,
                    'snippet': snippet.strip()[:300]
                })
        
        return results
    
    def get_content_for_topic(self, topic: str, file_type: str = 'markdown') -> str:
        """
        Search for content about a topic and format it for a file.
        
        Args:
            topic: The topic to search for
            file_type: Type of file to create (markdown, notes, etc.)
            
        Returns:
            Formatted content string
        """
        # Search for the topic
        search_query = f"{topic} overview guide explanation"
        results = self.search(search_query, max_results=3)
        
        if not results:
            return self._generate_fallback_content(topic, file_type)
        
        # Build content from search results
        content = f"# {topic}\n\n"
        content += f"*Generated from web search on {topic}*\n\n"
        
        for i, result in enumerate(results, 1):
            content += f"## {result['title']}\n\n"
            content += f"{result['snippet']}\n\n"
            if result['url']:
                content += f"*Source: {result['url']}*\n\n"
        
        content += "---\n\n"
        content += f"*This content was automatically gathered from web search results. "
        content += f"Please verify information from original sources.*\n"
        
        return content
    
    def _generate_fallback_content(self, topic: str, file_type: str) -> str:
        """Generate basic content when web search fails."""
        content = f"# {topic}\n\n"
        content += f"## Overview\n\n"
        content += f"This document covers the topic of **{topic}**.\n\n"
        content += f"## Key Points\n\n"
        content += f"- {topic} is a subject that requires further research\n"
        content += f"- This file was created as a starting point\n"
        content += f"- Content can be expanded based on specific needs\n\n"
        content += f"## Next Steps\n\n"
        content += f"1. Research {topic} from authoritative sources\n"
        content += f"2. Add specific details and examples\n"
        content += f"3. Organize content into logical sections\n\n"
        content += f"---\n\n"
        content += f"*Note: Web search was unavailable. This is a template for manual completion.*\n"
        
        return content


# Test when run directly
if __name__ == "__main__":
    ws = WebSearch()
    print("Testing web search...")
    results = ws.search("Python async programming")
    for r in results[:3]:
        print(f"- {r['title']}: {r['snippet'][:100]}...")
    
    print("\nGenerating content for 'Python async programming'...")
    content = ws.get_content_for_topic("Python async programming")
    print(content[:500])