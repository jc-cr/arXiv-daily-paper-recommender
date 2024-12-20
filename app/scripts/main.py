import os
import email
import re
import json
import subprocess
from datetime import datetime
from typing import List, Tuple
from dataclasses import dataclass

@dataclass
class Paper:
    title: str
    authors: str
    abstract: str
    link: str
    categories: str

class ArxivRecommender:
    def __init__(self, api_key: str, model_name: str = "gpt-4o"):
        self.api_key = api_key
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.model_name = model_name 
        
    def calculate_cost(self, input_tokens: int, output_tokens: int, model: str = "gpt-4o-mini") -> float:
        """Calculate cost based on token usage."""
        if model == "gpt-4o-mini":
            # Mini model pricing
            input_cost_per_million = 0.15  # $0.15 per 1M tokens
            output_cost_per_million = 0.60  # $0.60 per 1M tokens
        elif model == "gpt-4o":
            # Standard model pricing
            input_cost_per_million = 2.50   # $2.50 per 1M tokens
            output_cost_per_million = 10.00  # $10.00 per 1M tokens
            
        input_cost = (input_tokens / 1_000_000) * input_cost_per_million
        output_cost = (output_tokens / 1_000_000) * output_cost_per_million
        return input_cost + output_cost

    def get_user_profile(self, profile_path: str) -> str:
        """Read user profile from file."""
        with open(profile_path, 'r') as f:
            profile = f.read().strip()
            print("\n=== User Profile ===")
            print(profile)
            print("==================\n")
            return profile

    def rank_papers(self, papers: List[Paper], user_profile: str, top_n: int = 5) -> Tuple[List[Paper], dict]:
        """Rank papers based on user profile using OpenAI API. Returns ranked papers and token usage."""
        if not papers:
            print("No papers to rank!")
            return [], {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            
        papers_text = "\n\n".join([
            f"Paper {i+1}:\nTitle: {p.title}\nCategories: {p.categories}\nAbstract: {p.abstract}"
            for i, p in enumerate(papers)
        ])

        data = {
            "model": f"{self.model_name}",
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
            
            # Extract token usage
            usage = response['usage']
            input_tokens = usage.get('prompt_tokens', 0)
            output_tokens = usage.get('completion_tokens', 0)
            total_tokens = usage.get('total_tokens', 0)
            
            # Update total token counts
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            
            # Calculate and display costs
            cost = self.calculate_cost(input_tokens, output_tokens, "gpt-4o")  # Note: using gpt-4o here
            
            print("\n=== Token Usage ===")
            print(f"Input tokens: {input_tokens:,}")
            print(f"Output tokens: {output_tokens:,}")
            print(f"Total tokens: {total_tokens:,}")
            print(f"Estimated cost: ${cost:.6f}")
            print("===================")
            
            response_text = response['choices'][0]['message']['content'].strip()
            print(f"API Response: {response_text}")
            
            # Parse indices (1-based) from response
            indices = [int(i.strip()) - 1 for i in response_text.split(',')]
            ranked_papers = [papers[i] for i in indices if 0 <= i < len(papers)]
            
            return ranked_papers, {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "cost": cost
            }
            
        except Exception as e:
            print(f"Error in ranking: {e}")
            return papers[:top_n], {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost": 0}

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

    def generate_output(self, papers: List[Paper], token_usage: dict, output_path: str):
        """Generate JSON output file with recommended papers and token usage."""
        today = datetime.now().strftime("%Y-%m-%d")
        
        output_data = {
            "date": today,
            "token_usage": {
                "input_tokens": token_usage["input_tokens"],
                "output_tokens": token_usage["output_tokens"],
                "total_tokens": token_usage["total_tokens"],
                "estimated_cost_usd": token_usage["cost"]
            },
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
        
        # Print final token usage summary
        print("\n=== Final Token Usage Summary ===")
        print(f"Total Input Tokens: {self.total_input_tokens:,}")
        print(f"Total Output Tokens: {self.total_output_tokens:,}")
        print(f"Total Tokens: {self.total_input_tokens + self.total_output_tokens:,}")
        total_cost = self.calculate_cost(self.total_input_tokens, self.total_output_tokens, "gpt-4o")  # Using gpt-4o here too
        print(f"Total Estimated Cost: ${total_cost:.6f}")
        print("=============================")

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
    ranked_papers, token_usage = recommender.rank_papers(papers, user_profile)  # Note: unpacking tuple here
    
    # Generate output
    output_path = os.path.join("output", f"recommended_papers_{datetime.now().strftime('%Y%m%d')}.json")
    recommender.generate_output(ranked_papers, token_usage, output_path)

if __name__ == "__main__":
    main()