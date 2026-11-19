document.addEventListener('DOMContentLoaded', () => {
  const menu = document.querySelector('.notification-menu');
  if (!menu) return;

  const toggle = menu.querySelector('.notification-toggle');
  const dropdown = menu.querySelector('.notification-dropdown');
  const preview = menu.querySelector('.notification-preview');
  const count = menu.querySelector('[data-notification-count]');
  const endpoint = menu.dataset.notificationsUrl;

  const appendText = (parent, tag, text, className) => {
    const element = document.createElement(tag);
    element.textContent = text;
    if (className) element.className = className;
    parent.append(element);
    return element;
  };

  const render = (data) => {
    count.textContent = String(data.unread_count);
    count.hidden = data.unread_count === 0;
    preview.replaceChildren();

    if (data.notifications.length === 0) {
      appendText(preview, 'p', "You're all caught up.", 'notification-empty');
      return;
    }

    data.notifications.forEach((item) => {
      const link = document.createElement('a');
      link.className = `notification-preview-item${item.read_at ? '' : ' unread'}`;
      link.href = item.event_url || '/notifications/';
      appendText(link, 'strong', item.title);
      appendText(link, 'span', item.message);
      preview.append(link);
    });
  };

  const refresh = async () => {
    try {
      const response = await fetch(endpoint, {
        headers: { Accept: 'application/json' },
        credentials: 'same-origin',
      });
      if (!response.ok) throw new Error('Unable to refresh notifications.');
      render(await response.json());
    } catch (error) {
      preview.dataset.error = error.message;
      if (!dropdown.hidden && !preview.querySelector('.notification-error')) {
        const notice = appendText(preview, 'p', 'Notifications could not be refreshed.', 'notification-empty notification-error');
        notice.setAttribute('role', 'status');
      }
    }
  };

  toggle.addEventListener('click', () => {
    const opening = dropdown.hidden;
    dropdown.hidden = !opening;
    toggle.setAttribute('aria-expanded', String(opening));
    if (opening) refresh();
  });

  document.addEventListener('click', (event) => {
    if (!menu.contains(event.target)) {
      dropdown.hidden = true;
      toggle.setAttribute('aria-expanded', 'false');
    }
  });

  window.setInterval(refresh, 25000);
});
