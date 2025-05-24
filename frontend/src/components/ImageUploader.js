document.addEventListener('DOMContentLoaded', () => {
  const imageInput = document.getElementById('image-input');
  const previewContainer = document.getElementById('preview-container');

  imageInput.addEventListener('change', (event) => {
    const file = event.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = () => {
        previewContainer.innerHTML = `<img src="${reader.result}" alt="Vista previa" />`;
      };
      reader.readAsDataURL(file);
    }
  });
});
