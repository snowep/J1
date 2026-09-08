import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse


class Internet:
    """JARVIS Internet Module — On-demand web browsing with user approval."""

    def __init__(self, research_path='workspace/research'):
        project_root = os.path.dirname(os.path.dirname(__file__))
        self.research_dir = os.path.normpath(os.path.join(project_root, research_path))
        os.makedirs(self.research_dir, exist_ok=True)
        self.enabled = True
        self.requires_approval = True

    def is_enabled(self):
        return self.enabled

    def enable(self):
        self.enabled = True
        return "🌐 Internet access enabled."

    def disable(self):
        self.enabled = False
        return "🌐 Internet access disabled."

    def _is_valid_url(self, url):
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False

    def _fetch_url(self, url, timeout=30):
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        try:
            response = requests.get(url, headers=headers, timeout=timeout, verify=False)
            response.raise_for_status()
            return response.text, None
        except requests.exceptions.Timeout:
            return None, "Request timed out."
        except requests.exceptions.HTTPError as e:
            return None, f"HTTP error: {e.response.status_code}"
        except Exception as e:
            return None, str(e)

    def _extract_text(self, html):
        try:
            soup = BeautifulSoup(html, 'html.parser')
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()
            text = soup.get_text(separator='\n')
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            return text[:5000]
        except Exception as e:
            return f"Error parsing content: {e}"

    def _extract_title(self, html):
        try:
            soup = BeautifulSoup(html, 'html.parser')
            title = soup.find('title')
            return title.string.strip() if title else "Untitled Page"
        except:
            return "Untitled Page"

    def browse(self, url, save=False):
        if not self.enabled:
            return {'success': False, 'error': 'Internet access is disabled.'}
        if not self._is_valid_url(url):
            return {'success': False, 'error': 'Invalid URL format.'}
        
        html, error = self._fetch_url(url)
        if error:
            return {'success': False, 'error': error}
        
        text = self._extract_text(html)
        title = self._extract_title(html)
        
        result = {
            'success': True,
            'url': url,
            'title': title,
            'content': text,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
        
        if save:
            safe_name = re.sub(r'[^\w\s-]', '', title).replace(' ', '_')[:50]
            filename = f"{safe_name}.md"
            filepath = os.path.join(self.research_dir, filename)
            content = f"# {title}\n\n**Source:** {url}\n**Fetched:** {result['timestamp']}\n\n---\n\n{text}"
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                result['saved'] = filepath
            except Exception as e:
                result['save_error'] = str(e)
        
        return result

    def search(self, query, num_results=3):
        if not self.enabled:
            return {'success': False, 'error': 'Internet access is disabled.'}
        try:
            url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=15, verify=False)
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for result in soup.select('.result')[:num_results]:
                link = result.select_one('.result__a')
                snippet = result.select_one('.result__snippet')
                if link:
                    results.append({
                        'title': link.get_text(strip=True),
                        'url': link.get('href'),
                        'snippet': snippet.get_text(strip=True) if snippet else ''
                    })
            return {'success': True, 'query': query, 'results': results}
        except Exception as e:
            return {'success': False, 'error': str(e)}


if __name__ == "__main__":
    print("Testing JARVIS Internet Module...")
    inet = Internet()
    print(f"Enabled: {inet.is_enabled()}")
    print(inet.disable())
    print(inet.enable())
    print("\nFetching example.com...")
    result = inet.browse("https://example.com", save=False)
    print(f"Success: {result['success']}")
    if result['success']:
        print(f"Title: {result['title']}")