document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('upload-form');
  const imageInput = document.getElementById('image-input');
  const previewImage = document.getElementById('preview-image');
  const resultsList = document.getElementById('results-list');
  const nResultsInput = document.getElementById('n-results');

  // API URLs with fallback support
  const API_URLS = [
    'http://localhost:8000',
    'https://brandmatch-api-1815.onrender.com'
  ];

  // Function to try multiple API URLs
  async function tryAPICall(endpoint, options) {
    for (let i = 0; i < API_URLS.length; i++) {
      try {
        const response = await fetch(`${API_URLS[i]}${endpoint}`, options);
        if (response.ok) {
          return { response, apiUrl: API_URLS[i] };
        }
      } catch (error) {
        console.log(`Failed to connect to ${API_URLS[i]}: ${error.message}`);
        if (i === API_URLS.length - 1) {
          throw new Error('All API endpoints failed');
        }
      }
    }
  }

  // Preview functionality
  imageInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
      previewImage.src = URL.createObjectURL(file);
    }
  });

  // Form submission
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const file = imageInput.files[0];
    if (!file) {
      resultsList.innerHTML = '<div class="result-card">❌ Please select an image first</div>';
      return;
    }

    // Validate file type
    if (!file.type.startsWith('image/')) {
      resultsList.innerHTML = '<div class="result-card">❌ Please select a valid image file</div>';
      return;
    }

    const formData = new FormData();
    formData.append('file', file);
    
    const n_results = parseInt(nResultsInput.value) || 5;
    
    // Show loading state
    resultsList.innerHTML = '<div class="result-card">⏳ Searching...</div>';

    try {
      const { response, apiUrl } = await tryAPICall(`/search?n_results=${n_results}`, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();
      
      // Clear results
      resultsList.innerHTML = '';
      
      if (data?.matches && data.matches.length > 0) {
        data.matches.forEach(match => {
          const similarityPercent = ((1 - match.distance) * 100).toFixed(1);
          
          const resultCard = document.createElement('div');
          resultCard.className = 'result-card';
          resultCard.innerHTML = `
            <img src="${apiUrl}${match.imageUrl}" 
                 alt="${match.filename}" 
                 loading="lazy"
                 onerror="this.style.display='none'; this.nextElementSibling.style.display='block';" />
            <div style="display:none; padding: 2rem; text-align: center; color: #999;">
              Image not available
            </div>
            <div class="result-info">
              <div>${match.filename}</div>
              <div class="similarity-score">
                Similarity: ${similarityPercent}%
              </div>
            </div>
          `;
          resultsList.appendChild(resultCard);
        });
      } else {
        resultsList.innerHTML = '<div class="result-card">❌ No matches found</div>';
      }
    } catch (error) {
      console.error('Search failed:', error);
      resultsList.innerHTML = `<div class="result-card">❌ Error: ${error.message}</div>`;
    }
  });
});