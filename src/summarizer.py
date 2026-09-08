import os
import re
from datetime import datetime
from src.file_manager import FileManager


class Summarizer:
    """JARVIS Summarizer — Extract knowledge and create summaries from workspace files."""

    def __init__(self, summaries_path='workspace/summaries', workspace_path='workspace'):
        project_root = os.path.dirname(os.path.dirname(__file__))
        self.summaries_dir = os.path.normpath(os.path.join(project_root, summaries_path))
        self.workspace_path = os.path.normpath(os.path.join(project_root, workspace_path))
        os.makedirs(self.summaries_dir, exist_ok=True)
        self.fm = FileManager(workspace_path=workspace_path)

    def _extract_tags(self, content):
        """Extract hashtags or tags from content."""
        tags = re.findall(r'#(\w+)', content)
        return list(set(tags))

    def _extract_key_points(self, content, num_points=5):
        """Extract key points as bullet list."""
        lines = [l.strip() for l in content.split('\n') if l.strip() and len(l) > 30]
        key_points = []
        for line in lines:
            if any(kw in line.lower() for kw in ['##', '###', '- ', '* ', '**', '1.', '2.']):
                key_points.append(line.lstrip('#-* ').strip())
            if len(key_points) >= num_points:
                break
        if not key_points and lines:
            key_points = lines[:num_points]
        return key_points

    def _extract_title(self, content):
        """Extract title from markdown content."""
        for line in content.split('\n')[:5]:
            line = line.strip()
            if line.startswith('# '):
                return line[2:].strip()
        return "Untitled Document"

    def summarize_file(self, file_path, style='concise'):
        """
        Summarize a single file.
        
        Args:
            file_path: Path to file
            style: 'concise', 'bullets', or 'mindmap'
        
        Returns:
            Dict with success status and summary
        """
        result = self.fm.read(file_path)
        if not result['success']:
            return {'success': False, 'error': result['error']}
        
        content = result['content']
        title = self._extract_title(content) or file_path
        tags = self._extract_tags(content)
        key_points = self._extract_key_points(content)
        
        # Generate summary based on style
        if style == 'concise':
            summary = f"# Summary: {title}\n\n"
            summary += f"*Source: {file_path}*\n"
            summary += f"*Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*\n\n"
            summary += "---\n\n"
            summary += f"## Overview\n\n{content[:500]}...\n\n" if len(content) > 500 else f"## Overview\n\n{content}\n\n"
            if key_points:
                summary += "## Key Points\n\n" + '\n'.join(f"- {p}" for p in key_points[:5])
            
        elif style == 'bullets':
            summary = f"# {title} — Quick Reference\n\n"
            summary += f"*Source: {file_path}*\n\n"
            summary += "---\n\n"
            if tags:
                summary += f"**Tags:** {' '.join(f'#{t}' for t in tags)}\n\n"
            summary += "## Key Points\n\n" + '\n'.join(f"- {p}" for p in key_points)
            
        elif style == 'mindmap':
            summary = f"# {title}\n\n"
            summary += f"_Source: {file_path}_\n\n"
            summary += "---\n\n"
            if tags:
                summary += f"## Tags\n{', '.join(f'#{t}' for t in tags)}\n\n"
            summary += "## Main Points\n"
            for i, point in enumerate(key_points[:7], 1):
                summary += f"{i}. {point}\n"
            summary += "\n## Related\n- See also: [[index]]\n"
        
        else:
            summary = content  # Default to full content
        
        # Save summary
        safe_name = re.sub(r'[^\w\s-]', '', title).replace(' ', '_')[:40]
        summary_file = f"summary_{safe_name}.md"
        save_path = os.path.join(self.summaries_dir, summary_file)
        
        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(summary)
            return {
                'success': True,
                'title': title,
                'style': style,
                'tags': tags,
                'key_points': len(key_points),
                'summary_file': summary_file,
                'summary_path': save_path,
                'content': summary
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def summarize_directory(self, directory=None, style='concise'):
        """
        Summarize all markdown files in a directory.
        
        Args:
            directory: Path relative to workspace
            style: 'concise', 'bullets', or 'mindmap'
        
        Returns:
            Dict with combined summary
        """
        result = self.fm.list(directory)
        if not result['success']:
            return {'success': False, 'error': result['error']}
        
        md_files = [f for f in result.get('files', []) if f['name'].endswith('.md')]
        if not md_files:
            return {'success': False, 'error': 'No markdown files found'}
        
        combined_content = ""
        file_summaries = []
        
        for f in md_files:
            read_result = self.fm.read(f['name'])
            if read_result['success']:
                title = self._extract_title(read_result['content']) or f['name']
                combined_content += f"\n\n## {title}\n\n{read_result['content']}"
                file_summaries.append({
                    'file': f['name'],
                    'title': title,
                    'tags': self._extract_tags(read_result['content'])
                })
        
        # Create combined summary
        timestamp = datetime.utcnow().strftime('%Y-%m-%d')
        summary_file = f"combined_summary_{timestamp}.md"
        save_path = os.path.join(self.summaries_dir, summary_file)
        
        summary = f"# Combined Summary — {timestamp}\n\n"
        summary += f"*Files summarized: {len(file_summaries)}*\n\n"
        summary += "---\n\n"
        summary += "## Files Included\n\n"
        for fs in file_summaries:
            summary += f"- {fs['title']} (`{fs['file']}`)\n"
        
        summary += "\n## Combined Content\n" + combined_content
        
        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(summary)
            return {
                'success': True,
                'files_summarized': len(file_summaries),
                'summary_file': summary_file,
                'summary_path': save_path
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def extract_tags_all(self, directory=None):
        """Extract all tags from files in directory."""
        result = self.fm.list(directory)
        if not result['success']:
            return {'success': False, 'error': result['error']}
        
        md_files = [f for f in result.get('files', []) if f['name'].endswith('.md')]
        all_tags = {}
        
        for f in md_files:
            read_result = self.fm.read(f['name'])
            if read_result['success']:
                tags = self._extract_tags(read_result['content'])
                for tag in tags:
                    if tag not in all_tags:
                        all_tags[tag] = []
                    all_tags[tag].append(f['name'])
        
        # Create tag index
        index_content = f"# Tag Index — {datetime.utcnow().strftime('%Y-%m-%d')}\n\n"
        for tag, files in sorted(all_tags.items()):
            index_content += f"## #{tag}\n\n"
            for f in files:
                index_content += f"- [[{f}]]\n"
            index_content += "\n"
        
        tag_index_file = 'tag_index.md'
        save_path = os.path.join(self.summaries_dir, tag_index_file)
        
        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(index_content)
            return {
                'success': True,
                'total_tags': len(all_tags),
                'index_file': tag_index_file,
                'tags': all_tags
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def list_summaries(self):
        """List all summary files."""
        try:
            files = os.listdir(self.summaries_dir)
            summaries = [{'name': f, 'size': os.path.getsize(os.path.join(self.summaries_dir, f))} for f in sorted(files)]
            return {'success': True, 'summaries': summaries, 'count': len(summaries)}
        except Exception as e:
            return {'success': False, 'error': str(e)}


if __name__ == "__main__":
    print("Testing JARVIS Summarizer...")
    s = Summarizer()
    
    # List summaries
    result = s.list_summaries()
    print(f"Summaries: {result.get('count', 0)} files")
    
    # Summarize a file if exists
    test_file = 'test.md'
    result = s.summarize_file(test_file, style='concise')
    if result['success']:
        print(f"✅ Summarized: {result['summary_file']}")
        print(f"   Tags: {result['tags']}")
    else:
        print(f"❌ {result.get('error', 'Unknown error')}")