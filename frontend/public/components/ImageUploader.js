export function setupUploader() {
  const form = document.getElementById('upload-form');
  const imageInput = document.getElementById('image-input');
  const previewImage = document.getElementById('preview-image');
  const resultsList = document.getElementById('results-list');
  const nResultsInput = document.getElementById('n-results');

  const API_URL = import.meta.env.PUBLIC_API_URL;

  if (!form || !imageInput || !previewImage || !resultsList || !nResultsInput) {
    console.warn("Some DOM elements were not found.");
    return;
  }

  imageInput.addEventListener('change', () => {
    const file = imageInput.files[0];
    if (file && previewImage) {
      previewImage.src = URL.createObjectURL(file);
      console.log("Preview updated with:", file.name);
    }
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const file = imageInput.files[0];
    if (!file) {
      resultsList.innerHTML = `<div class="result-card">❌ Please select an image</div>`;
      return;
    }

    const formData = new FormData();
    formData.append('file', file);

    const n_results = parseInt(nResultsInput.value) || 5;

    resultsList.innerHTML = `<div class="result-card">⏳ Searching...</div>`;

    try {
      const response = await fetch(`${API_URL}/search?n_results=${n_results}`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) throw new Error("Server error");

      const data = await response.json();
      resultsList.innerHTML = '';

      if (data?.matches?.length) {
        data.matches.forEach(match => {
          const similarityPercent = ((1 - match.distance) * 100).toFixed(1);
          const card = document.createElement('div');
          card.className = 'result-card';
          card.innerHTML = `
            <img src="${API_URL}${match.imageUrl}" alt="${match.filename}" />
            <div class="result-info">
              <div>${match.filename}</div>
              <div class="similarity-score">Similarity: ${similarityPercent}%</div>
            </div>`;
          resultsList.appendChild(card);
        });
      } else {
        resultsList.innerHTML = `<div class="result-card">❌ No matches found</div>`;
      }
    } catch (err) {
      resultsList.innerHTML = `<div class="result-card">❌ Error: ${err.message}</div>`;
    }
  });
}



/* document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('upload-form');
  const imageInput = document.getElementById('image-input');
  const previewImage = document.getElementById('preview-image');
  const resultsList = document.getElementById('results-list');
  const nResultsInput = document.getElementById('n-results');

  //replacing API_URL
  const API_URL = import.meta.env.PUBLIC_API_URL;
  //const API_URL = 'http://localhost:8000';

  imageInput.addEventListener('change', () => {
  const file = imageInput.files[0];
  if (file && previewImage) {
    previewImage.src = URL.createObjectURL(file);
  }
  console.log(file);
});

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const file = imageInput.files[0];
    if (!file) {
      resultsList.innerHTML = `<div class="result-card">❌ Please select an image</div>`;
      return;
    }    const formData = new FormData();
    formData.append('file', file);
    
    // Convert n_results to a URL parameter since FormData doesn't handle query parameters
    const n_results = parseInt(nResultsInput.value) || 5;

    resultsList.innerHTML = `<div class="result-card">⏳ Searching...</div>`;    try {
      const response = await fetch(`${API_URL}/search?n_results=${n_results}`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error("Server error");
      }

      const data = await response.json();
      resultsList.innerHTML = '';

      if (data?.matches && data.matches.length > 0) {
        data.matches.forEach(match => {
          const resultCard = document.createElement('div');
          resultCard.className = 'result-card';
          
          // Calculate similarity percentage (1 - distance, converted to percentage)
          const similarityPercent = ((1 - match.distance) * 100).toFixed(1);
          
          resultCard.innerHTML = `
            <img src="${API_URL}${match.imageUrl}" 
                 alt="${match.filename}" 
                 loading="lazy"
                 onerror="this.onerror=null; this.src='data:image/svg+xml,%3Csvg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'100\\' height=\\'100\\'%3E%3Crect width=\\'100\\' height=\\'100\\' fill=\\'%23eee\\'/%3E%3Ctext x=\\'50%25\\' y=\\'50%25\\' text-anchor=\\'middle\\' dy=\\'.3em\\' fill=\\'%23aaa\\'%3EError%3C/text%3E%3C/svg%3E';" />
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
        resultsList.innerHTML = `<div class="result-card">❌ No matches found</div>`;
      }
    } catch (err) {
      resultsList.innerHTML = `<div class="result-card">❌ Error: ${err.message}</div>`;
    }
  });
});

 */