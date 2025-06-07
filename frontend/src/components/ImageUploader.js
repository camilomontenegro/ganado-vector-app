document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('upload-form');
  const imageInput = document.getElementById('image-input');
  const previewContainer = document.getElementById('preview-container');
  const resultsList = document.getElementById('results-list');

  imageInput.addEventListener('change', () => {
    const file = imageInput.files[0];
    previewContainer.innerHTML = '';
    if (file) {
      const img = document.createElement('img');
      img.src = URL.createObjectURL(file);
      img.alt = 'Preview';
      img.classList.add('preview-img');
      previewContainer.appendChild(img);
    }
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const file = imageInput.files[0];
    if (!file) {
      resultsList.innerHTML = `<li>❌ Please select an image</li>`;
      return;
    }

    const formData = new FormData();
    formData.append('file', file);

    resultsList.innerHTML = `<li>⏳ Searching...</li>`;

    try {
      const response = await fetch('http://localhost:8000/search', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error("Server error");
      }

      const data = await response.json();

      resultsList.innerHTML = '';

      if (data?.result) {
        const li = document.createElement('li');
        li.innerHTML = `
          ✅ Match found: <strong>${data.result.filename}</strong><br />
          🔢 Distance: ${data.distance.toFixed(2)}
        `;
        resultsList.appendChild(li);
      } else {
        resultsList.innerHTML = `<li>❌ No match found</li>`;
      }
    } catch (err) {
      resultsList.innerHTML = `<li>❌ Error: ${err.message}</li>`;
    }
  });
});

