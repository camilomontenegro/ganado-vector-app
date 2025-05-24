document.addEventListener('DOMContentLoaded', () => {
  const imageInput = document.getElementById('image-input');
  const previewContainer = document.getElementById('preview-container');
  const uploadForm = document.getElementById('upload-form');
  const resultsList = document.getElementById('results-list');

  // Preview image
  imageInput.addEventListener('change', (event) => {
    const file = event.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = () => {
        previewContainer.innerHTML = `<img src="${reader.result}" alt="Preview" style="max-width:100%; border:1px solid #ccc; border-radius:4px;" />`;
      };
      reader.readAsDataURL(file);
    }
  });

  // Submit form (mock fetch)
  uploadForm.addEventListener('submit', (e) => {
    e.preventDefault();

    // Clear previous results
    resultsList.innerHTML = "";

    // Simulated delay and fake results
    setTimeout(() => {
      const fakeResults = [
        { id: 'BR001', similarity: 0.96 },
        { id: 'BR014', similarity: 0.89 },
        { id: 'BR007', similarity: 0.85 },
      ];

      fakeResults.forEach(result => {
        const li = document.createElement('li');
        li.textContent = `Brand ID: ${result.id} – Similarity: ${(result.similarity * 100).toFixed(1)}%`;
        resultsList.appendChild(li);
      });
    }, 1000);
  });
});
