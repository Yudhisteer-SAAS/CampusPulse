document.addEventListener('DOMContentLoaded', () => {
  const navToggle = document.querySelector('.nav-toggle');
  const navMenu = document.querySelector('.main-nav');

  if (navToggle && navMenu) {
    navToggle.addEventListener('click', () => {
      const isOpen = navMenu.classList.toggle('is-open');
      navToggle.setAttribute('aria-expanded', String(isOpen));
    });

    navMenu.querySelectorAll('a').forEach((link) => {
      link.addEventListener('click', () => {
        if (window.innerWidth <= 760) {
          navMenu.classList.remove('is-open');
          navToggle.setAttribute('aria-expanded', 'false');
        }
      });
    });
  }

  const reveals = document.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.1 });

    reveals.forEach((element) => observer.observe(element));
  } else {
    reveals.forEach((element) => element.classList.add('is-visible'));
  }

  document.querySelectorAll('.toast-close').forEach((button) => {
    button.addEventListener('click', () => {
      const toast = button.closest('.toast');
      if (toast) {
        toast.remove();
      }
    });
  });

  const starInputs = document.querySelectorAll('.star-rating input');
  starInputs.forEach((input) => {
    input.addEventListener('change', () => {
      const selectedValue = input.value;
      document.querySelectorAll('.star-rating label').forEach((label) => {
        const currentFor = label.getAttribute('for');
        const isSelected = currentFor === `star${selectedValue}`;
        label.style.color = isSelected ? '#d36a4f' : 'rgba(24,35,45,0.18)';
      });
    });
  });
});
