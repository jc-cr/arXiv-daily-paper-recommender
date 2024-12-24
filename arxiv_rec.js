// DOM Elements
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const currentFile = document.getElementById('currentFile');
const submitBtn = document.getElementById('submitBtn');
const error = document.getElementById('error');
const loading = document.getElementById('loading');
const recommendations = document.getElementById('recommendations');
const userBio = document.querySelector('.user-bio');
const apiKey = document.querySelector('.user-api-key');
const numRecommendations = document.getElementById('numRecommendations');
const selected_model = document.getElementById('selected_model');

let selectedFile = null;

// Event Listeners for drag and drop
dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    handleFile(e.dataTransfer.files[0]);
});

dropZone.addEventListener('click', () => {
    fileInput.click();
});

fileInput.addEventListener('change', (e) => {
    handleFile(e.target.files[0]);
});

function handleFile(file) {
    if (!file) return;
    
    if (!file.name.endsWith('.eml')) {
        error.textContent = 'Please upload a .eml file';
        return;
    }

    selectedFile = file;
    currentFile.textContent = file.name;
    error.textContent = '';
    updateSubmitButton();
}

userBio.addEventListener('input', updateSubmitButton);
apiKey.addEventListener('input', updateSubmitButton);

function updateSubmitButton() {
    submitBtn.disabled = !selectedFile || !userBio.value.trim() || !apiKey.value.trim();
}

submitBtn.addEventListener('click', async () => {
    if (!selectedFile || !userBio.value.trim() || !apiKey.value.trim()) return;

    error.textContent = '';
    loading.style.display = 'block';
    recommendations.innerHTML = '';
    submitBtn.disabled = true;

    try {
        const reader = new FileReader();
        
        reader.onload = async (e) => {
            try {
                const content = e.target.result;
                const papers = parseEml(content);
                
                if (papers.length === 0) {
                    throw new Error('No papers found in the email');
                }

                console.log(`Successfully parsed ${papers.length} papers`);
                
                const rankedPapers = await rankPapers(
                    papers, 
                    userBio.value.trim(), 
                    parseInt(numRecommendations.value), 
                    apiKey.value.trim()
                );
                
                displayRecommendations(rankedPapers);
            } catch (err) {
                console.error('Error processing papers:', err);
                error.textContent = err.message || 'An error occurred while processing papers';
            } finally {
                loading.style.display = 'none';
                submitBtn.disabled = false;
            }
        };

        reader.readAsText(selectedFile);
    } catch (err) {
        console.error('Error reading file:', err);
        error.textContent = 'Failed to read file. Please try again.';
        loading.style.display = 'none';
        submitBtn.disabled = false;
    }
});

// Parse the .eml file content
function parseEml(content) {
    // Remove header until first paper section (matching Python implementation)
    const sections = content.split('------------------------------------------------------------------------------\\\\');
    const papersContent = sections[sections.length - 1]; // Take last section like Python

    if (!papersContent || !papersContent.includes('arXiv:')) {
        throw new Error('No papers section found in email');
    }

    // Split into individual papers
    const papers = [];
    let currentPaper = '';
    const lines = papersContent.split('\n');
    
    for (let line of lines) {
        if (line.startsWith('arXiv:')) {
            if (currentPaper) {
                papers.push(currentPaper);
            }
            currentPaper = line + '\n';
        } else if (currentPaper) {
            currentPaper += line + '\n';
        }
    }
    
    if (currentPaper) {
        papers.push(currentPaper);
    }

    // Parse each paper's details with regex patterns matching Python
    return papers.map(paperText => {
        // Match Python's regex patterns exactly
        const arxivMatch = paperText.match(/arXiv:(\d+\.\d+)/);
        const titleMatch = paperText.match(/Title:(.*?)(?=Authors:|$)/s);
        const authorsMatch = paperText.match(/Authors:(.*?)(?=Categories:|Comments:|$)/s);
        const categoriesMatch = paperText.match(/Categories:(.*?)(?=\n|$)/);
        
        // Fixed abstract extraction to match Python implementation
        const parts = paperText.split('\\\\');
        let abstract = '';
        if (parts.length >= 2) {
            abstract = parts[1].trim();
            // Remove the link part at the end if present
            const linkIndex = abstract.lastIndexOf('( https://arxiv.org');
            if (linkIndex !== -1) {
                abstract = abstract.substring(0, linkIndex).trim();
            }
        }

        if (!titleMatch || !arxivMatch) {
            console.log('Failed to parse paper:', paperText.substring(0, 100));
            return null;
        }

        const paper = {
            title: titleMatch[1].trim().replace(/\n\s+/g, ' '),
            authors: authorsMatch ? authorsMatch[1].trim().replace(/\n\s+/g, ' ') : "Unknown",
            abstract: abstract.replace(/\n\s+/g, ' '),
            link: `https://arxiv.org/abs/${arxivMatch[1]}`,
            categories: categoriesMatch ? categoriesMatch[1].trim() : ""
        };

        return paper;
    }).filter(paper => paper !== null);
}

async function rankPapers(papers, userProfile, topN, apiKey) {
    if (!papers || papers.length === 0) {
        throw new Error('No papers to rank');
    }

    if (papers.length === 1) {
        console.log('Single paper case - returning paper directly');
        return papers;
    }

    const papersFormatted = papers.map((paper, idx) => ({
        id: idx + 1,
        title: paper.title,
        categories: paper.categories,
        abstract: paper.abstract
    }));

    const BATCH_SIZE = 15;
    const paperBatches = [];
    for (let i = 0; i < papersFormatted.length; i += BATCH_SIZE) {
        paperBatches.push(papersFormatted.slice(i, i + BATCH_SIZE));
    }

    console.log(`Split ${papersFormatted.length} papers into ${paperBatches.length} batches`);

    const paperScores = [];
    
    for (let batchIndex = 0; batchIndex < paperBatches.length; batchIndex++) {
        console.log(`Processing batch ${batchIndex + 1}/${paperBatches.length}`);
        const batch = paperBatches[batchIndex];
        const startIdx = batchIndex * BATCH_SIZE;

        // Ensure response has exact number of scores needed
        const requestBody = {
            model: selected_model.value,
            messages: [
                {
                    role: "developer",
                    content: `You are a research paper scorer. Return a JSON object with a "scores" array containing EXACTLY ${batch.length} numbers between 1-10.

Score based on relevance:
10: Perfect match - Essential reading
7-9: Highly relevant - Strong overlap
4-6: Moderately relevant - Some relevance
1-3: Minimally relevant - Limited connection

Example format for ${batch.length} papers:
{"scores": [${Array(batch.length).fill('7').join(', ')}]}`
                },
                {
                    role: "user",
                    content: `Score these ${batch.length} papers based on relevance to the profile.

User Profile:
${userProfile}

Papers to Score:
${batch.map(p => 
    `Paper ${p.id}:
    Title: ${p.title}
    Categories: ${p.categories}
    Abstract: ${p.abstract}`
).join('\n\n')}`
                }
            ],
            temperature: 0.1,
            max_tokens: 150,
            response_format: {
                type: "json_schema",
                json_schema: {
                    name: "paper_scores_schema",
                    schema: {
                        type: "object",
                        properties: {
                            scores: {
                                type: "array",
                                description: `Array of exactly ${batch.length} paper scores (1-10)`,
                                items: {
                                    type: "number",
                                    minimum: 1,
                                    maximum: 10
                                },
                                minItems: batch.length,
                                maxItems: batch.length
                            }
                        },
                        required: ["scores"],
                        additionalProperties: false
                    }
                }
            }
        };

        try {
            const response = await fetch('https://api.openai.com/v1/chat/completions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${apiKey.trim()}`
                },
                body: JSON.stringify(requestBody)
            });

            if (!response.ok) {
                const errorText = await response.text();
                console.error(`API Error Response: ${errorText}`);
                throw new Error('OpenAI API request failed: ' + errorText);
            }

            const data = await response.json();
            console.log(`Batch ${batchIndex + 1} API Response:`, data);

            try {
                const content = JSON.parse(data.choices[0].message.content);
                
                // Validate scores array exists and has correct length
                if (!content || !Array.isArray(content.scores) || content.scores.length !== batch.length) {
                    console.error('Invalid response format:', content);
                    throw new Error(`Invalid scores array - expected length ${batch.length}, got ${content.scores?.length}`);
                }

                // Validate and normalize each score
                const scores = content.scores.map(score => {
                    const num = Number(score);
                    if (isNaN(num)) throw new Error('Invalid score: not a number');
                    return Math.max(1, Math.min(10, Math.round(num))); // Ensure valid range and integer
                });

                console.log(`Batch ${batchIndex + 1} scores:`, scores);

                // Add validated scores to global list
                scores.forEach((score, localIdx) => {
                    const globalIdx = startIdx + localIdx;
                    paperScores.push({
                        index: globalIdx,
                        score: score,
                        batchNumber: batchIndex + 1
                    });
                });

            } catch (parseError) {
                console.error(`Error parsing batch ${batchIndex + 1}:`, parseError);
                console.error('Raw content:', data.choices[0].message.content);
                // Skip this batch and continue with next one
                continue;
            }

        } catch (error) {
            console.error(`Error processing batch ${batchIndex + 1}:`, error);
            continue;
        }

        // Add delay between requests
        if (batchIndex < paperBatches.length - 1) {
            await new Promise(resolve => setTimeout(resolve, 500));
        }
    }

    // Ensure we have at least some valid scores
    if (paperScores.length === 0) {
        throw new Error('No valid paper rankings received from API');
    }

    // Log scoring distribution
    const scoreDistribution = paperScores.reduce((acc, {score}) => {
        acc[score] = (acc[score] || 0) + 1;
        return acc;
    }, {});
    console.log('Score distribution:', scoreDistribution);

    // Sort and get top papers
    const topPapers = paperScores
        .sort((a, b) => b.score - a.score)
        .slice(0, topN)
        .map(item => ({
            ...papers[item.index],
            score: item.score,
            batchNumber: item.batchNumber
        }));

    console.log('Top papers with scores:', topPapers.map(p => ({
        title: p.title.substring(0, 50) + '...',
        score: p.score,
        batchNumber: p.batchNumber
    })));

    return topPapers;
}

// Modified display function to truncate abstracts only for rendering
function displayRecommendations(papers) {
    if (!papers || papers.length === 0) {
        recommendations.innerHTML = '<p>No papers found to display.</p>';
        return;
    }

    const truncateStr = (str, maxLen = 150) => {
        if (!str) return '';
        return str.length > maxLen ? str.substring(0, maxLen) + '...' : str;
    };

    const html = papers.map((paper, index) => `
        <div class="paper-card">
            <h3>${paper.title || 'No Title'}</h3>
            ${paper.score ? `<div class="score">Relevance Score: ${paper.score}/10</div>` : ''}
            <div class="authors">${paper.authors || 'Unknown Authors'}</div>
            <div class="abstract">${truncateStr(paper.abstract) || 'No abstract available'}</div>
            <a href="${paper.link}" class="link" target="_blank">Read on arXiv</a>
        </div>
    `).join('');

    recommendations.innerHTML = html;
}