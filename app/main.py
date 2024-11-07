import os
import email
import re
from datetime import datetime
from typing import List, Dict
from anthropic import Anthropic
from dataclasses import dataclass

@dataclass
class Paper:
    title: str
    authors: str
    abstract: str
    link: str
    categories: str

class ArxivRecommender:
    def __init__(self, anthropic_api_key: str):
        self.client = Anthropic(api_key=anthropic_api_key)
        
    def parse_eml(self, eml_path: str) -> List[Paper]:
        """Parse .eml file and extract paper information."""
        with open(eml_path, 'r') as f:
            msg = email.message_from_file(f)
            
        content = msg.get_payload()
        papers = []
        
        # Split content into individual paper entries
        paper_entries = content.split('\\\\')[1:]  # Skip header
        
        for entry in paper_entries:
            if not entry.strip():
                continue
                
            # Extract paper details using regex
            title_match = re.search(r'Title: (.*?)(?=Authors:|$)', entry, re.DOTALL)
            authors_match = re.search(r'Authors: (.*?)(?=Categories:|$)', entry, re.DOTALL)
            abstract_match = re.search(r'\n\n  (.*?)\\', entry, re.DOTALL)
            arxiv_id_match = re.search(r'arXiv:(\d+\.\d+)', entry)
            categories_match = re.search(r'Categories: (.*?)(?=\n|$)', entry)
            
            if title_match and abstract_match and arxiv_id_match:
                paper = Paper(
                    title=title_match.group(1).strip(),
                    authors=authors_match.group(1).strip() if authors_match else "Unknown",
                    abstract=abstract_match.group(1).strip(),
                    link=f"https://arxiv.org/abs/{arxiv_id_match.group(1)}",
                    categories=categories_match.group(1).strip() if categories_match else ""
                )
                papers.append(paper)
                
        return papers

    def get_user_profile(self, profile_path: str) -> str:
        """Read user profile from file."""
        with open(profile_path, 'r') as f:
            return f.read().strip()

    def rank_papers(self, papers: List[Paper], user_profile: str, top_n: int = 5) -> List[Paper]:
        """Rank papers based on user profile using Claude."""
        papers_text = "\n\n".join([
            f"Title: {p.title}\nCategories: {p.categories}\nAbstract: {p.abstract}"
            for p in papers
        ])
        
        prompt = f"""Based on the user's research profile below, rank the following papers in order of relevance. 
        Consider both the technical fit and potential impact for the user's work.
        
        User Profile:
        {user_profile}
        
        Papers:
        {papers_text}
        
        Return only the indexes of the top {top_n} papers in order of relevance, comma-separated (e.g., "2,5,1,3,4")."""

        response = self.client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=1000,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Parse response to get ordered indices
        try:
            indices = [int(i.strip()) - 1 for i in response.content[0].text.split(',')]
            return [papers[i] for i in indices if i < len(papers)]
        except:
            # Fallback to first top_n papers if ranking fails
            return papers[:top_n]

    def generate_markdown(self, papers: List[Paper], output_path: str):
        """Generate markdown file with recommended papers."""
        today = datetime.now().strftime("%Y-%m-%d")
        
        md_content = [f"# Top {len(papers)} Papers of {today} for You\n"]
        
        for paper in papers:
            md_content.extend([
                f"## {paper.title}",
                f"### Link",
                f"{paper.link}",
                f"### Authors",
                f"{paper.authors}",
                f"### Abstract",
                f"{paper.abstract}\n"
            ])
            
        with open(output_path, 'w') as f:
            f.write('\n'.join(md_content))

def main():
    # Get API key from environment variable
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable is required")
    
    recommender = ArxivRecommender(api_key)
    
    # Process the most recent .eml file in input directory
    input_dir = "input"
    eml_files = [f for f in os.listdir(input_dir) if f.endswith('.eml')]
    if not eml_files:
        raise FileNotFoundError("No .eml files found in input directory")
    
    latest_eml = max(eml_files, key=lambda x: os.path.getctime(os.path.join(input_dir, x)))
    eml_path = os.path.join(input_dir, latest_eml)
    
    # Read user profile
    profile_path = os.path.join(input_dir, "user_profile.txt")
    
    # Process papers
    papers = recommender.parse_eml(eml_path)
    user_profile = recommender.get_user_profile(profile_path)
    ranked_papers = recommender.rank_papers(papers, user_profile)
    
    # Generate output
    output_path = os.path.join("output", f"recommended_papers_{datetime.now().strftime('%Y%m%d')}.md")
    recommender.generate_markdown(ranked_papers, output_path)

if __name__ == "__main__":
    main()