/**
 * chatbot-widget.js
 *
 * Drop-in chat widget for The Graduate Route's website.
 *
 * Usage on the actual site:
 *   <script>
 *     window.GRADUATE_ROUTE_CHAT_API = "https://your-deployed-backend.onrender.com/chat";
 *   </script>
 *   <script src="https://your-deployed-backend.onrender.com/widget/chatbot-widget.js"></script>
 *
 * If GRADUATE_ROUTE_CHAT_API is not set, it falls back to localhost for local testing.
 */
(function () {
  const API_URL = window.GRADUATE_ROUTE_CHAT_API || "http://localhost:5000/chat";

  // The Graduate Route brand palette, pulled from the logo
  const COLORS = {
    sage: "#82986f",        // circle background
    sageLight: "#eef1e9",   // tinted background for bot bubbles
    terracotta: "#a86840",  // signpost
    terracottaDark: "#8f5734",
    charcoal: "#33363d",    // signpost
    cream: "#f5f2ea",       // text on dark
    gradient: "linear-gradient(135deg, #ef0574 0%, #ff4931 55%, #f2a300 100%)",
  };

  const style = document.createElement("style");
  style.textContent = `
    #gr-chat-bubble {
      position: fixed; bottom: 24px; right: 24px; width: 60px; height: 60px;
      border-radius: 50%; background: ${COLORS.gradient}; display: flex;
      align-items: center; justify-content: center; cursor: pointer;
      box-shadow: 0 4px 14px rgba(0,0,0,0.3); z-index: 9999; padding: 4px;
    }
    #gr-chat-bubble img { width: 100%; height: 100%; border-radius: 50%; object-fit: cover; }
    #gr-chat-window {
      position: fixed; bottom: 96px; right: 24px; width: 340px; max-height: 480px;
      background: #fff; border-radius: 14px; box-shadow: 0 8px 30px rgba(0,0,0,0.25);
      display: none; flex-direction: column; overflow: hidden; z-index: 9999;
      font-family: -apple-system, Segoe UI, Roboto, sans-serif;
      border: 1px solid ${COLORS.sage}33;
    }
    #gr-chat-header {
      background: ${COLORS.charcoal}; color: ${COLORS.cream}; padding: 12px 16px;
      font-weight: 600; font-size: 14px; display: flex; align-items: center; gap: 8px;
    }
    #gr-chat-header img { width: 24px; height: 24px; border-radius: 50%; }
    #gr-chat-messages {
      flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column;
      gap: 8px; min-height: 240px; background: #fbfbf9;
    }
    .gr-msg { padding: 8px 12px; border-radius: 10px; max-width: 85%; font-size: 14px; line-height: 1.4; }
    .gr-msg.user { align-self: flex-end; background: ${COLORS.terracotta}; color: ${COLORS.cream}; }
    .gr-msg.bot { align-self: flex-start; background: ${COLORS.sageLight}; color: ${COLORS.charcoal}; white-space: pre-wrap; }
    #gr-chat-input-row { display: flex; border-top: 1px solid #e5e7eb; }
    #gr-chat-input { flex: 1; border: none; padding: 10px 12px; font-size: 14px; outline: none; }
    #gr-chat-send {
      border: none; background: ${COLORS.terracotta}; color: ${COLORS.cream};
      padding: 0 16px; cursor: pointer; font-size: 14px; font-weight: 600;
    }
    #gr-chat-send:hover { background: ${COLORS.terracottaDark}; }
  `;
  document.head.appendChild(style);

  // Resolve the logo: use an explicit override if the page sets one
  // (the main site does, since its assets live under /static/img), otherwise
  // fall back to a "logo.png" sitting next to this script (for standalone use).
  const scriptEl = document.currentScript;
  const LOGO_URL = window.GRADUATE_ROUTE_LOGO_URL || new URL("logo.png", scriptEl.src).href;

  const bubble = document.createElement("div");
  bubble.id = "gr-chat-bubble";
  bubble.innerHTML = `<img src="${LOGO_URL}" alt="The Graduate Route" />`;

  const win = document.createElement("div");
  win.id = "gr-chat-window";
  win.innerHTML = `
    <div id="gr-chat-header"><img src="${LOGO_URL}" alt="" /> Ask The Graduate Route</div>
    <div id="gr-chat-messages"></div>
    <div id="gr-chat-input-row">
      <input id="gr-chat-input" type="text" placeholder="Ask about our services..." />
      <button id="gr-chat-send">Send</button>
    </div>
  `;

  document.body.appendChild(bubble);
  document.body.appendChild(win);

  const messagesEl = win.querySelector("#gr-chat-messages");
  const inputEl = win.querySelector("#gr-chat-input");
  const sendBtn = win.querySelector("#gr-chat-send");

  let history = [];
  let opened = false;

  bubble.addEventListener("click", () => {
    opened = !opened;
    win.style.display = opened ? "flex" : "none";
    if (opened && messagesEl.children.length === 0) {
      addMessage(
        "bot",
        "Hi! Tell me what you're applying for or what kind of support you're looking for, and I'll point you to the right service."
      );
    }
  });

  function addMessage(role, text) {
    const div = document.createElement("div");
    div.className = `gr-msg ${role}`;
    div.innerText = text;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  async function sendMessage() {
    const text = inputEl.value.trim();
    if (!text) return;
    inputEl.value = "";
    addMessage("user", text);
    history.push({ role: "user", text });

    const typingEl = addMessage("bot", "Typing...");

    try {
      const res = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history }),
      });
      const data = await res.json();
      typingEl.remove();
      const answer = data.answer || "Sorry, something went wrong. Please try again.";
      addMessage("bot", answer);
      history.push({ role: "bot", text: answer });
    } catch (err) {
      typingEl.remove();
      addMessage("bot", "Sorry, I couldn't reach the server. Please try again shortly.");
    }
  }

  sendBtn.addEventListener("click", sendMessage);
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendMessage();
  });
})();
