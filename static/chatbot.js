const chatToggleBtn = document.getElementById('chatToggleBtn');
const chatWidget = document.getElementById('chatWidget');
const chatCloseBtn = document.getElementById('chatCloseBtn');
const chatForm = document.getElementById('chatForm');
const chatInput = document.getElementById('chatInput');
const chatMessages = document.getElementById('chatMessages');

function appendChatBubble(text, cls) {
    if (!chatMessages) return;
    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${cls}`;
    bubble.textContent = text;
    chatMessages.appendChild(bubble);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function setChatVisible(visible) {
    if (!chatWidget) return;
    chatWidget.classList.toggle('hidden', !visible);
    if (visible && chatInput) chatInput.focus();
}

if (chatToggleBtn) {
    chatToggleBtn.addEventListener('click', () => setChatVisible(true));
}

if (chatCloseBtn) {
    chatCloseBtn.addEventListener('click', () => setChatVisible(false));
}

if (chatForm) {
    chatForm.addEventListener('submit', async event => {
        event.preventDefault();
        const question = (chatInput?.value || '').trim();
        if (!question) return;

        appendChatBubble(question, 'user');
        if (chatInput) chatInput.value = '';

        try {
            const response = await fetch('/api/rag/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: question }),
            });
            const payload = await response.json();
            let botText = payload.answer || 'No answer available.';
            if (payload.sources && payload.sources.length > 0) {
                botText += '\n\nSources:';
                payload.sources.forEach(src => {
                    const title = src.title || src.vehicle_id || 'Reference';
                    botText += `\n• ${title}`;
                });
            }
            appendChatBubble(botText, 'bot');
        } catch (error) {
            appendChatBubble('Unable to reach the assistant right now.', 'bot');
        }
    });
}