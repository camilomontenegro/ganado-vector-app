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

  // ─── Warm-up ──────────────────────────────────────────────────────────────
  // The Render Web Service sleeps when idle and takes ~100s to wake — measured,
  // not estimated. Almost all of that is Render starting the container, not our
  // code, so it cannot be optimised away from here.
  //
  // Firing one cheap request the moment the page loads means the server wakes
  // while the user is still choosing a file, instead of only after they press
  // Find Matches. This does NOT make anything faster; it overlaps the wait with
  // something the user was going to spend time on anyway.
  let apiAwake = false;
  const warmUpStartedAt = Date.now();

  async function warmUp() {
    for (const base of API_URLS) {
      try {
        const response = await fetch(`${base}/`, { method: 'GET' });
        if (response.ok) {
          apiAwake = true;
          const seconds = ((Date.now() - warmUpStartedAt) / 1000).toFixed(1);
          console.log(`API ready via ${base} after ${seconds}s`);
          return;
        }
      } catch (error) {
        // Expected for localhost when only the deployed API is running.
      }
    }
  }
  warmUp();

  // Elapsed-time message shown while a cold server is still starting up.
  function startWakingMessage() {
    const startedAt = Date.now();
    const render = () => {
      const elapsed = Math.round((Date.now() - startedAt) / 1000);
      resultsList.innerHTML = apiAwake
        ? `<div class="result-card">⏳ Searching… (${elapsed}s)</div>`
        : `<div class="result-card">
             ⏳ Waking the server — this can take up to two minutes on the free
             tier, and only happens after it has been idle.<br />
             <small>${elapsed}s elapsed. It stays fast once awake.</small>
           </div>`;
    };
    render();
    return setInterval(render, 1000);
  }

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
    
    // Show loading state — ticks, and says WHY it is slow when the server is cold.
    const waitingTimer = startWakingMessage();

    try {
      const { response, apiUrl } = await tryAPICall(`/search?n_results=${n_results}`, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();
      apiAwake = true;          // it answered, so it is up
      clearInterval(waitingTimer);

      // Clear results
      resultsList.innerHTML = '';
      
      if (data?.matches && data.matches.length > 0) {
        data.matches.forEach(match => {
          // ChromaDB is queried with its default space, which is SQUARED L2 —
          // not cosine. For the unit vectors the API stores, ||a-b||² = 2 - 2·cos,
          // so cos = 1 - distance/2. Dividing by 2 is what keeps this a percentage.
          //
          // Without it, anything past distance 1.0 renders negative: the worst
          // pair in the current index sits at 1.66 and displayed -65.6%.
          // MobileNetV2 ends in ReLU6, so every component is non-negative, which
          // bounds cosine to [0,1] and distance to [0,2] — hence 0-100% here.
          // Swap in a model with signed features (CLIP, say) and that guarantee
          // is gone; clamp at that point.
          const similarityPercent = ((1 - match.distance / 2) * 100).toFixed(1);
          
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
      clearInterval(waitingTimer);
      console.error('Search failed:', error);
      resultsList.innerHTML = `<div class="result-card">❌ Error: ${error.message}</div>`;
    }
  });
});