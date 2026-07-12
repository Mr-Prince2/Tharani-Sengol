document.addEventListener("DOMContentLoaded", () => {
    const chatForm = document.getElementById("ragChatForm");
    const chatInput = document.getElementById("ragChatInput");
    const chatHistory = document.getElementById("ragChatHistory");

    // Expose query setter globally for helper buttons
    window.setQuery = (query) => {
        chatInput.value = query;
        chatInput.focus();
    };

    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const question = chatInput.value.trim();
        if (!question) return;

        // 1. Add User Bubble
        appendBubble("user", question);
        chatInput.value = "";

        // 2. Add Loading Bot Bubble
        const loadingId = "msg_loading_" + Date.now();
        appendBubble("bot", "Thinking...", loadingId);
        chatHistory.scrollTop = chatHistory.scrollHeight;

        try {
            const res = await fetch("/api/rag/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ question: question })
            });
            const data = await res.json();

            // Replace loading bubble
            const loadingBubble = document.getElementById(loadingId);
            if (loadingBubble) {
                loadingBubble.remove();
            }

            // Append bot response with badge and source panels
            appendBotResponse(data);

        } catch (err) {
            console.error("RAG fetch error:", err);
            const loadingBubble = document.getElementById(loadingId);
            if (loadingBubble) {
                loadingBubble.innerHTML = `<div class="message-content" style="color: var(--danger);">Error connecting to RAG assistant backend.</div>`;
            }
        }
        chatHistory.scrollTop = chatHistory.scrollHeight;
    });

    function appendBubble(sender, text, id = null) {
        const bubble = document.createElement("div");
        bubble.className = `chat-message ${sender}`;
        if (id) bubble.id = id;
        bubble.innerHTML = `<div class="message-content">${escapeHTML(text)}</div>`;
        chatHistory.appendChild(bubble);
    }

    function appendBotResponse(data) {
        const bubble = document.createElement("div");
        bubble.className = "chat-message bot";
        
        // Grounded Badge
        const badgeType = data.grounded_in === "live_data" ? "live_data" : "documents";
        const badgeLabel = data.grounded_in === "live_data" ? "Live Telemetry" : "Regulation Corpus";
        
        let html = `<span class="grounded-badge ${badgeType}">${badgeLabel}</span>`;
        
        // Message Text
        html += `<div class="message-content">${formatAnswerText(data.answer)}</div>`;
        
        // Source citation panel
        if (data.sources && data.sources.length > 0) {
            html += `<div class="sources-panel">`;
            html += `<div class="sources-header">Sources & Citations:</div>`;
            
            data.sources.forEach(src => {
                if (data.grounded_in === "live_data") {
                    if (src.vehicle_id) {
                        html += `<div class="source-tag"><strong>Vehicle ${src.vehicle_id}:</strong> Risk: ${src.risk} | Threat: ${src.final_threat_score} | Weight: ${src.predicted_weight}t</div>`;
                    } else if (src.alert_time) {
                        html += `<div class="source-tag"><strong>Alert (Lorry ${src.vehicle_id}):</strong> ${src.message}</div>`;
                    } else if (src.event_time) {
                        html += `<div class="source-tag"><strong>Violation (Lorry ${src.vehicle_id}):</strong> ${src.reason}</div>`;
                    } else if (src.permit_id) {
                        html += `<div class="source-tag"><strong>Permit ${src.permit_id}:</strong> Max Trips ${src.max_trips} | Completed ${src.completed_trips}</div>`;
                    }
                } else {
                    html += `<div class="source-tag"><strong>${escapeHTML(src.title)}</strong> (Similarity: ${src.similarity})<br><span class="muted" style="font-size: 11px;">"${escapeHTML(src.text)}"</span></div>`;
                }
            });
            
            html += `</div>`;
        }
        
        bubble.innerHTML = html;
        chatHistory.appendChild(bubble);
    }

    function formatAnswerText(text) {
        // Escape standard HTML, then replace newline with br
        return escapeHTML(text).replace(/\n/g, "<br>");
    }

    function escapeHTML(str) {
        if (!str) return "";
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
});
