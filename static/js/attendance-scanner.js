document.addEventListener('DOMContentLoaded', () => {
  const video = document.querySelector('#attendance-camera');
  const form = document.querySelector('#attendance-form');
  const codeInput = document.querySelector('#pass-code');
  const status = document.querySelector('#scanner-status');
  const startButton = document.querySelector('#scanner-start');
  if (!video || !form || !codeInput || !status || !window.QrScanner) {
    return;
  }

  let scanner;
  let submitted = false;

  const stopScanner = async () => {
    if (scanner) {
      await scanner.stop();
    }
  };

  const startScanner = async () => {
    if (location.protocol !== 'https:' && location.hostname !== 'localhost') {
      status.textContent = 'Camera scanning requires HTTPS or localhost. Use the manual pass-code option below.';
      startButton.hidden = true;
      return;
    }

    if (!scanner) {
      scanner = new window.QrScanner(
        video,
        async (result) => {
          if (submitted) return;
          submitted = true;
          codeInput.value = result.data;
          status.textContent = 'Pass found. Verifying attendance…';
          await stopScanner();
          form.requestSubmit();
        },
        {
          returnDetailedScanResult: true,
          highlightScanRegion: true,
          highlightCodeOutline: true,
          preferredCamera: 'environment',
        },
      );
    }

    try {
      await scanner.start();
      status.textContent = 'Camera ready. Center the QR pass in the frame.';
      startButton.hidden = true;
    } catch (error) {
      status.textContent = 'Camera unavailable. Check camera permission or enter the pass code manually.';
      startButton.hidden = false;
    }
  };

  startButton.addEventListener('click', startScanner);
  startScanner();
  window.addEventListener('pagehide', stopScanner, { once: true });
});
