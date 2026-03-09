/* ========================================
   PDFPilot — Voice Input
   Web Speech API for mic commands
   ======================================== */

document.addEventListener('DOMContentLoaded', () => {

  const micBtn = document.getElementById('micBtn');
  const chatInput = document.getElementById('chatInput');

  if (!micBtn || !chatInput) return;

  // Check browser support
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognition) {
    micBtn.title = 'Voice input not supported in this browser';
    micBtn.style.opacity = '0.4';
    micBtn.style.cursor = 'not-allowed';
    return;
  }

  const recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.lang = 'en-US';

  let isRecording = false;

  micBtn.addEventListener('click', () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  });

  function startRecording() {
    isRecording = true;
    micBtn.classList.add('recording');
    micBtn.title = 'Listening... Click to stop';
    chatInput.placeholder = 'Listening...';

    try {
      recognition.start();
    } catch (e) {
      // Already started
      stopRecording();
    }
  }

  function stopRecording() {
    isRecording = false;
    micBtn.classList.remove('recording');
    micBtn.title = 'Voice input';
    chatInput.placeholder = 'Tell PDFPilot what to do...';

    try {
      recognition.stop();
    } catch (e) {
      // Already stopped
    }
  }

  // Speech result
  recognition.onresult = (event) => {
    let transcript = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      transcript += event.results[i][0].transcript;
    }

    chatInput.value = transcript;
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';

    // Auto-send when speech is final
    if (event.results[event.results.length - 1].isFinal) {
      stopRecording();
      // Trigger send after a short delay
      setTimeout(() => {
        const sendBtn = document.getElementById('sendBtn');
        if (sendBtn) sendBtn.click();
      }, 400);
    }
  };

  // Error
  recognition.onerror = (event) => {
    console.warn('Speech recognition error:', event.error);
    stopRecording();

    if (event.error === 'not-allowed') {
      alert('Microphone access denied. Please allow microphone access in your browser settings.');
    }
  };

  // End
  recognition.onend = () => {
    if (isRecording) {
      stopRecording();
    }
  };

});
