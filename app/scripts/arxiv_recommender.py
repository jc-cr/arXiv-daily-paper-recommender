import os
import email
import re
import json
import subprocess
from typing import List, Tuple
from dataclasses import dataclass
from datetime import datetime

import time

@dataclass
class Paper:
    title: str
    authors: str
    abstract: str
    link: str
    categories: str

class ArxivRecommender:
    def __init__(self, api_key: str, model_name: str = "gpt-4o-mini"):
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

        # Create a temporary file in the input directory (which we know exists from docker-compose)
        tmp_file_path = os.path.join('app','temp', 'temp_request.json')
        os.makedirs(os.path.dirname(tmp_file_path), exist_ok=True)
        with open(tmp_file_path, 'w') as tmp_file:
            json.dump(data, tmp_file)

        max_retries = 1
        base_delay = 1  # Start with 1 second delay
        
        for attempt in range(max_retries):
            try:
                print(f"\nMaking API request (attempt {attempt + 1}/{max_retries})...")
                
                # Use curl with data from file
                curl_cmd = [
                    'curl', 'https://api.openai.com/v1/chat/completions',
                    '-H', f'Authorization: Bearer {self.api_key}',
                    '-H', 'Content-Type: application/json',
                    '-d', '@' + tmp_file_path  # '@' tells curl to read from file
                ]

                result = subprocess.run(curl_cmd, capture_output=True, text=True)
                
                # Check if we got a rate limit error
                if "429" in result.stderr or "Too Many Requests" in result.stderr:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    print(f"Rate limit hit. Waiting {delay} seconds before retry...")
                    time.sleep(delay)
                    continue
                    
                response = json.loads(result.stdout)
                
                # Clean up the temporary file
                os.remove(tmp_file_path)
                
                # Extract token usage
                usage = response['usage']
                input_tokens = usage.get('prompt_tokens', 0)
                output_tokens = usage.get('completion_tokens', 0)
                total_tokens = usage.get('total_tokens', 0)
                
                # Update total token counts
                self.total_input_tokens += input_tokens
                self.total_output_tokens += output_tokens
                
                # Calculate and display costs
                cost = self.calculate_cost(input_tokens, output_tokens, "gpt-4o")
                
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
                print(f"Error in attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:  # If this was our last attempt
                    # Clean up the temporary file
                    try:
                        os.remove(tmp_file_path)
                    except OSError:
                        print("Warning: Could not remove temporary file")
                    return papers[:top_n], {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost": 0}
                
                # If not the last attempt, wait before trying again
                delay = base_delay * (2 ** attempt)
                print(f"Waiting {delay} seconds before retry...")
                time.sleep(delay)

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
            
            abstract_match = re.search(r'(?:Comments:.*?\n)?.*?\\\\\n\s+(.*?)(?=\\\\|\( https://arxiv\.org)', paper_text, re.DOTALL)
            
            
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
