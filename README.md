# arXiv Daily Paper Recommender

An AI-powered tool that recommends relevant arXiv papers based on your research interests. It processes your daily arXiv email subscriptions and generates a personalized list of the most relevant papers using the Anthropic Claude API.

## Features

- Processes arXiv email subscription content (.eml files)
- Ranks papers based on your research interests using AI
- Generates a clean markdown file with recommended papers
- Containerized for easy deployment

## Prerequisites

- Docker and Docker Compose
- Anthropic API key

## Setup

1. Clone the repository:
```bash
git clone https://github.com/jc-cr/arXiv-daily-paper-recommender.git
cd arXiv-daily-paper-recommender
```

2. Create a `.env` file in the the projects directory with your Anthropic API key:
```bash
ANTHROPIC_API_KEY=your_api_key_here
```

3. Build the docker image:
```bash
cd .docker
docker compose build
```

4.  Set up your research profile:
   - Edit `app/input/user_profile.txt` to describe your research interests and current projects

5. Place your arXiv subscription .eml file in the `app/input` directory
Note: You can get the .eml file by downloading the email from your email client. (e.g., Gmail -> More -> Download message)

## Usage

1. Run the recommender:
```bash
cd .docker
docker compose up
```

2. Find your recommendations in `app/output/recommended_papers_YYYYMMDD.md`
Note: If you are moving the file you may need to change the permissions to access it. `sudo chown -R $(whoami):$(whoami) app/output`

## Examples

### user_profile.txt

Describe your research interests, current projects, and relevant technical background. For example:
```
Current Research:
- Computer vision for medical imaging
- Deep learning architectures for 3D segmentation
- Transfer learning in limited data scenarios

Technical Interests:
- Transformer architectures
- Self-supervised learning
- Uncertainty estimation in deep learning
```