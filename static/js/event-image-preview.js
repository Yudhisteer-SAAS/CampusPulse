document.addEventListener('DOMContentLoaded', () => {
  const posterInput = document.querySelector('#poster');
  const posterPreview = document.querySelector('#poster-preview');
  const galleryInput = document.querySelector('#gallery-images');
  const galleryPreview = document.querySelector('#gallery-preview');

  if (posterInput && posterPreview) {
    posterInput.addEventListener('change', () => {
      posterPreview.querySelectorAll('img').forEach((image) => URL.revokeObjectURL(image.src));
      posterPreview.replaceChildren();
      const file = posterInput.files?.[0];
      if (!file) return;
      const image = document.createElement('img');
      image.src = URL.createObjectURL(file);
      image.alt = 'Selected poster preview';
      image.className = 'upload-preview-image';
      posterPreview.append(image);
    });
  }

  if (!galleryInput || !galleryPreview) return;

  let selectedFiles = new DataTransfer();

  const renderGallery = () => {
    galleryPreview.querySelectorAll('img').forEach((image) => URL.revokeObjectURL(image.src));
    galleryPreview.replaceChildren();
    Array.from(selectedFiles.files).forEach((file, index) => {
      const item = document.createElement('div');
      item.className = 'upload-preview-item';
      const image = document.createElement('img');
      image.src = URL.createObjectURL(file);
      image.alt = `Selected gallery image ${index + 1}`;
      image.className = 'upload-preview-image';
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'button button-outline small';
      remove.textContent = 'Remove';
      remove.addEventListener('click', () => {
        const remaining = new DataTransfer();
        Array.from(selectedFiles.files).forEach((selected, selectedIndex) => {
          if (selectedIndex !== index) remaining.items.add(selected);
        });
        selectedFiles = remaining;
        galleryInput.files = selectedFiles.files;
        renderGallery();
      });
      item.append(image, remove);
      galleryPreview.append(item);
    });
  };

  galleryInput.addEventListener('change', () => {
    const updated = new DataTransfer();
    Array.from(selectedFiles.files).forEach((file) => updated.items.add(file));
    Array.from(galleryInput.files || []).forEach((file) => updated.items.add(file));
    selectedFiles = updated;
    galleryInput.files = selectedFiles.files;
    renderGallery();
  });
});
