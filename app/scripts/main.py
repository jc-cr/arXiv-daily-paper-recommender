from quart import Quart, request, render_template, jsonify
import os
from arxiv_recommender import ArxivRecommender
import json
from datetime import datetime

# Initialize Quart app with Docker-compatible paths
app = Quart(__name__, template_folder='/app/templates')

# Create directories if they don't exist
os.makedirs('/app/input', exist_ok=True)
os.makedirs('/app/output', exist_ok=True)

# Initialize the recommender
api_key = os.getenv('API_KEY')
recommender = ArxivRecommender(api_key)

@app.route('/')
async def index():
    return await render_template('index.html')

@app.route('/upload', methods=['POST'])
async def upload():
    try:
        # Get the number of recommendations to return
        top_n = int(request.args.get('top_n', 5))

        # Get the user bio
        form = await request.form
        user_bio = form.get('user_bio', '')
        # Save user bio to input directory
        user_bio_path = '/app/input/user_bio.txt'
        with open(user_bio_path, 'w') as f:
            f.write(user_bio)
        
        # Get the uploaded file
        files = await request.files
        if 'eml_file' not in files:
            return jsonify({'error': 'No file uploaded'}), 400
            
        file = files['eml_file']
        if not file.filename.endswith('.eml'):
            return jsonify({'error': 'Invalid file type'}), 400
        
        # Save the file to input directory
        file_path = '/app/input/uploaded.eml'
        await file.save(file_path)
        
        # Process the file and get recommendations
        papers = recommender.parse_eml(file_path)
        ranked_papers, token_usage = recommender.rank_papers(papers, user_bio, top_n)

        # Generate output file
        output_path = os.path.join('/app/output', f'recommended_papers_{datetime.now().strftime("%Y%m%d")}.json')
        recommender.generate_output(ranked_papers, token_usage, output_path)
        
        # Format recommendations for display
        recommendations = []
        for paper in ranked_papers:
            recommendations.append({
                'title': paper.title,
                'authors': paper.authors,
                'abstract': paper.abstract[:150] + '...' if len(paper.abstract) > 150 else paper.abstract,
                'link': paper.link,
                'categories': paper.categories
            })
        
        return jsonify({
            'status': 'success',
            'recommendations': recommendations
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)