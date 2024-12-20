import os
import email
import re
import json
import subprocess
from datetime import datetime
from typing import List
from dataclasses import dataclass

@dataclass
class Paper:
    title: str
    authors: str
    abstract: str
    link: str
    categories: str

class ArxivRecommender:
    def __init__(self, api_key: str):
        self.api_key = api_key
        
    def parse_eml(self, eml_path: str) -> List[Paper]:
        """Parse .eml file and extract paper information."""
        with open(eml_path, 'r') as f:
            msg = email.message_from_file(f)
            
        content = msg.get_payload()
        
        # Remove header until first paper
        content = content.split('------------------------------------------------------------------------------\\\\')[-1]
        
        # Split into papers, but keep abstracts with their papers
        papers = []
        current_paper = ""
        lines = content.split('\n')
        
        for line in lines:
            if line.startswith('arXiv:'):
                if current_paper:  # Save previous paper if exists
                    papers.append(current_paper)
                current_paper = line + '\n'
            else:
                current_paper += line + '\n'
                
        if current_paper:  # Add last paper
            papers.append(current_paper)
            
        print(f"\nFound {len(papers)} papers")
        
        parsed_papers = []
        for i, paper_text in enumerate(papers):
            # Extract paper details using revised regex patterns
            arxiv_match = re.search(r'arXiv:(\d+\.\d+)', paper_text)
            title_match = re.search(r'Title: (.*?)(?=Authors:|$)', paper_text, re.DOTALL)
            authors_match = re.search(r'Authors: (.*?)(?=Categories:|Comments:|$)', paper_text, re.DOTALL)
            categories_match = re.search(r'Categories: (.*?)(?=\n|$)', paper_text)
            
            # Abstract is the indented text after the metadata
            abstract_match = re.search(r'\n\n  (.+?)(?=\n\n|$)', paper_text, re.DOTALL)
            
            if title_match and arxiv_match:  # Only require title and arxiv ID
                paper = Paper(
                    title=title_match.group(1).strip().replace('\n  ', ' '),
                    authors=authors_match.group(1).strip().replace('\n  ', ' ') if authors_match else "Unknown",
                    abstract=abstract_match.group(1).strip().replace('\n  ', ' ') if abstract_match else "",
                    link=f"https://arxiv.org/abs/{arxiv_match.group(1)}",
                    categories=categories_match.group(1).strip() if categories_match else ""
                )
                parsed_papers.append(paper)
                
                # Debug output for first few papers
                if i < 2:
                    print(f"\nPaper {i+1}:")
                    print(f"Title: {paper.title[:100]}...")
                    print(f"Authors: {paper.authors[:100]}...")
                    print(f"Categories: {paper.categories}")
                    print(f"Link: {paper.link}")
                    print(f"Abstract: {paper.abstract[:100]}...")
        
        return parsed_papers

    def get_user_profile(self, profile_path: str) -> str:
        """Read user profile from file."""
        with open(profile_path, 'r') as f:
            profile = f.read().strip()
            print("\n=== User Profile ===")
            print(profile)
            print("==================\n")
            return profile

    def rank_papers(self, papers: List[Paper], user_profile: str, top_n: int = 5) -> List[Paper]:
        """Rank papers based on user profile using OpenAI API."""
        if not papers:
            print("No papers to rank!")
            return []
            
        papers_text = "\n\n".join([
            f"Paper {i+1}:\nTitle: {p.title}\nCategories: {p.categories}\nAbstract: {p.abstract}"
            for i, p in enumerate(papers)
        ])

        data = {
            "model": "gpt-4o-mini-2024-07-18",
            "messages": [
                {
                    "role": "developer",
                    "content": "You are a research paper recommender that ranks papers based on user research interests."
                },
                {
                    "role": "user",
                    "content": f"""Given the user's research profile, rank the papers by relevance.
                    Return only the paper numbers (1-based) in descending order of relevance, comma-separated.
                    Only return the top {top_n} most relevant papers.
                    
                    User Profile:
                    {user_profile}
                    
                    Papers:
                    {papers_text}"""
                }
            ],
            "temperature": 0.2,
            "max_tokens": 50
        }

        curl_cmd = [
            'curl', 'https://api.openai.com/v1/chat/completions',
            '-H', f'Authorization: Bearer {self.api_key}',
            '-H', 'Content-Type: application/json',
            '-d', json.dumps(data)
        ]

        try:
            print("\nMaking API request...")
            result = subprocess.run(curl_cmd, capture_output=True, text=True)
            response = json.loads(result.stdout)
            
            response_text = response['choices'][0]['message']['content'].strip()
            print(f"API Response: {response_text}")
            
            # Parse indices (1-based) from response
            indices = [int(i.strip()) - 1 for i in response_text.split(',')]
            return [papers[i] for i in indices if 0 <= i < len(papers)]
            
        except Exception as e:
            print(f"Error in ranking: {e}")
            return papers[:top_n]

    def generate_output(self, papers: List[Paper], output_path: str):
        """Generate JSON output file with recommended papers."""
        today = datetime.now().strftime("%Y-%m-%d")
        
        output_data = {
            "date": today,
            "recommendations": [
                {
                    "title": paper.title,
                    "authors": paper.authors,
                    "link": paper.link,
                    "categories": paper.categories,
                    "abstract": paper.abstract
                }
                for paper in papers
            ]
        }
            
        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"\nOutput saved to: {output_path}")
        
        # Debug: Print first recommendation
        if output_data["recommendations"]:
            print("\nFirst recommendation:")
            rec = output_data["recommendations"][0]
            print(f"Title: {rec['title']}")
            print(f"Categories: {rec['categories']}")
            print(f"Link: {rec['link']}")

def main():
    # Get API key from environment variable
    api_key = os.getenv('API_KEY')
    if not api_key:
        raise ValueError("API_KEY environment variable is not set")
    print("API key loaded (length):", len(api_key))
    
    recommender = ArxivRecommender(api_key)
    
    # Process the most recent .eml file in input directory
    input_dir = "input"
    eml_files = [f for f in os.listdir(input_dir) if f.endswith('.eml')]
    if not eml_files:
        raise FileNotFoundError("No .eml files found in input directory")
    
    latest_eml = max(eml_files, key=lambda x: os.path.getctime(os.path.join(input_dir, x)))
    eml_path = os.path.join(input_dir, latest_eml)
    print(f"\nProcessing EML file: {eml_path}")
    
    # Read user profile
    profile_path = os.path.join(input_dir, "user_profile.txt")
    
    # Process papers
    papers = recommender.parse_eml(eml_path)
    print(f"\nTotal papers parsed: {len(papers)}")
    
    user_profile = recommender.get_user_profile(profile_path)
    ranked_papers = recommender.rank_papers(papers, user_profile)
    
    # Generate output
    output_path = os.path.join("output", f"recommended_papers_{datetime.now().strftime('%Y%m%d')}.json")
    recommender.generate_output(ranked_papers, output_path)

if __name__ == "__main__":
    main()