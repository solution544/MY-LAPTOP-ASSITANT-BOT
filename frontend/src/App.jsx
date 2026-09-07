
import { useEffect, useRef, useState } from "react";
import {
  Menu,
  Settings,
  Mic,
  Paperclip,
  Send,
  X,
} from "lucide-react";
import useVoice from "./hooks/useVoice";
import "./App.css";

function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([]);
  const [selectedFiles, setSelectedFiles] = useState([]);

  const fileInputRef = useRef(null);

  const {
    isListening,
    isProcessing,
    transcript,
    reply,
    toggleListening,
  } = useVoice();

  // ==========================================================
  // SPACEBAR → TOGGLE VOICE
  // ==========================================================
  useEffect(() => {
    const handleVoiceShortcut = (event) => {
      const target = event.target;

      const isTyping =
        target?.tagName === "INPUT" ||
        target?.tagName === "TEXTAREA" ||
        target?.isContentEditable;

      if (event.code === "Space" && !isTyping) {
        event.preventDefault();
        toggleListening();
      }
    };

    window.addEventListener("keydown", handleVoiceShortcut);

    return () => {
      window.removeEventListener(
        "keydown",
        handleVoiceShortcut
      );
    };
  }, [toggleListening]);

  // ==========================================================
  // SEND TEXT MESSAGE
  // ==========================================================
  const handleSend = async () => {
    const trimmedMessage = message.trim();

    if (!trimmedMessage && selectedFiles.length === 0) {
      return;
    }

    if (trimmedMessage) {
      setMessages((prev) => [
        ...prev,
        {
          role: "user",
          content: trimmedMessage,
        },
      ]);
    }

    setMessage("");
    setSelectedFiles([]);

    try {
      const response = await fetch(
        "http://127.0.0.1:8000/api/chat",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            message: trimmedMessage,
          }),
        }
      );

      if (!response.ok) {
        const errorText = await response.text();

        throw new Error(
          errorText || "Failed to send message"
        );
      }

      const data = await response.json();

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            data.content ||
            "I completed the request.",
          confirmation_required:
            data.confirmation_required || false,
          confirmation_id:
            data.confirmation_id || null,
          tool_name:
            data.tool_name || null,
          description:
            data.description || null,
          permission_level:
            data.permission_level || null,
        },
      ]);
    } catch (error) {
      console.error("Chat error:", error);

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "Sorry, I couldn't connect to Solution AI's backend.",
        },
      ]);
    }
  };

  // ==========================================================
  // CONFIRMATION
  // ==========================================================
  const handleConfirmation = async (
    confirmationId,
    approved
  ) => {
    if (!confirmationId) {
      return;
    }

    try {
      const response = await fetch(
        "http://127.0.0.1:8000/api/chat/confirm",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            confirmation_id: confirmationId,
            approved,
          }),
        }
      );

      if (!response.ok) {
        const errorText = await response.text();

        throw new Error(
          errorText || "Confirmation request failed"
        );
      }

      const data = await response.json();

      console.log(
        "Chat confirmation result:",
        data
      );

      // Remove the confirmation buttons
      setMessages((prev) =>
        prev.map((msg) =>
          msg.confirmation_id === confirmationId
            ? {
                ...msg,
                confirmation_required: false,
              }
            : msg
        )
      );

      // Add backend response to chat
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            data.content ||
            (approved
              ? "Confirmed. The action has been completed."
              : "Okay. I cancelled the action."),
        },
      ]);
    } catch (error) {
      console.error(
        "Chat confirmation error:",
        error
      );

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "I couldn't process that confirmation.",
        },
      ]);
    }
  };

  // ==========================================================
  // ENTER → SEND
  // ==========================================================
  const handleKeyDown = (event) => {
    if (
      event.key === "Enter" &&
      !event.shiftKey
    ) {
      event.preventDefault();
      handleSend();
    }
  };

  // ==========================================================
  // FILE SELECTION
  // ==========================================================
  const handleFileChange = (event) => {
    const files = Array.from(
      event.target.files || []
    );

    if (files.length > 0) {
      setSelectedFiles((prev) => [
        ...prev,
        ...files,
      ]);
    }

    event.target.value = "";
  };

  // ==========================================================
  // REMOVE FILE
  // ==========================================================
  const removeFile = (index) => {
    setSelectedFiles((prev) =>
      prev.filter(
        (_, fileIndex) =>
          fileIndex !== index
      )
    );
  };

  // ==========================================================
  // UI
  // ==========================================================
  return (
    <div className="app">

      {/* ====================================================
          HEADER
      ==================================================== */}
      <header className="header">

        <button
          className="icon-button"
          onClick={() =>
            setMenuOpen(!menuOpen)
          }
          aria-label="Open menu"
        >
          <Menu size={24} />
        </button>

        <div className="logo">
          <span className="logo-dot"></span>
          SOLUTION AI
        </div>

        <button
          className="icon-button"
          aria-label="Settings"
        >
          <Settings size={22} />
        </button>

      </header>

      {/* ====================================================
          SIDEBAR
      ==================================================== */}
      <aside
        className={`sidebar ${
          menuOpen ? "open" : ""
        }`}
      >

        <div className="sidebar-title">
          SOLUTION AI
        </div>

        <button
          className="new-chat"
          onClick={() => {
            setMessages([]);
            setMessage("");
            setSelectedFiles([]);
          }}
        >
          + New Conversation
        </button>

        <nav>
          <button>
            💬 Conversations
          </button>

          <button>
            🕘 History
          </button>

          <button>
            ⚙️ Settings
          </button>
        </nav>

      </aside>

      {/* ====================================================
          MAIN
      ==================================================== */}
      <main className="main">

        {/* ==================================================
            ROBOT
        ================================================== */}
        <section className="robot-container">

          <div className="robot-glow"></div>

          <div className="robot">

            <div className="robot-head">

              <div className="antenna">
                <div className="antenna-light"></div>
              </div>

              <div className="robot-face">

                <div className="eyes">

                  <div className="eye"></div>

                  <div className="eye"></div>

                </div>

                <div className="mouth">
                  <div className="mouth-inner"></div>
                </div>

              </div>

            </div>

          </div>

          {/* VOICE STATUS */}
          <div className="voice-status">

            <span
              className={`status-dot ${
                isListening ? "active" : ""
              }`}
            ></span>

            <span>
              {isListening
                ? "Listening..."
                : isProcessing
                ? "Thinking..."
                : 'Say "Hey Solution"'}
            </span>

          </div>

          {/* VOICE TRANSCRIPT */}
          {transcript && (
            <div className="transcript">

              <span>You:</span>

              <p>{transcript}</p>

            </div>
          )}

          {/* VOICE REPLY */}
          {reply && (
            <div className="transcript">

              <span>Solution AI:</span>

              <p>{reply}</p>

            </div>
          )}

        </section>

        {/* ==================================================
            CHAT AREA
        ================================================== */}
        <section className="chat-area">

          {/* =================================================
              CHAT MESSAGES
          ================================================= */}
          <div className="chat-messages">

            {messages.map((msg, index) => (

              <div
                key={index}
                className={`chat-message ${msg.role}`}
              >

                <span>
                  {msg.role === "user"
                    ? "You"
                    : "Solution AI"}
                </span>

                <p>{msg.content}</p>

                {/* ==========================================
                    CONFIRMATION BUTTONS
                ========================================== */}
                {msg.confirmation_required &&
                  msg.confirmation_id && (
                    <div className="confirmation-buttons">

                      <button
                        className="confirmation-yes"
                        onClick={() =>
                          handleConfirmation(
                            msg.confirmation_id,
                            true
                          )
                        }
                      >
                        ✓ Yes
                      </button>

                      <button
                        className="confirmation-no"
                        onClick={() =>
                          handleConfirmation(
                            msg.confirmation_id,
                            false
                          )
                        }
                      >
                        ✕ No
                      </button>

                    </div>
                  )}

              </div>

            ))}

          </div>

          {/* =================================================
              SELECTED FILES
          ================================================= */}
          {selectedFiles.length > 0 && (
            <div className="selected-files">

              {selectedFiles.map(
                (file, index) => (

                  <div
                    className="file-preview"
                    key={`${file.name}-${index}`}
                  >

                    <span>
                      {file.name}
                    </span>

                    <button
                      onClick={() =>
                        removeFile(index)
                      }
                      aria-label={`Remove ${file.name}`}
                    >
                      <X size={15} />
                    </button>

                  </div>

                )
              )}

            </div>
          )}

          {/* =================================================
              CHAT BAR
          ================================================= */}
          <div className="chat-bar">

            {/* ATTACHMENT */}
            <button
              className="chat-icon-button"
              onClick={() =>
                fileInputRef.current?.click()
              }
              aria-label="Attach file"
            >
              <Paperclip size={21} />
            </button>

            <input
              ref={fileInputRef}
              type="file"
              multiple
              hidden
              onChange={handleFileChange}
            />

            {/* TEXT INPUT */}
            <input
              className="chat-input"
              type="text"
              value={message}
              onChange={(event) =>
                setMessage(
                  event.target.value
                )
              }
              onKeyDown={handleKeyDown}
              placeholder="Type a message..."
              autoComplete="off"
            />

            {/* MICROPHONE */}
            <button
              className={
                isListening
                  ? "chat-icon-button mic-active"
                  : "chat-icon-button"
              }
              onClick={toggleListening}
              aria-label="Activate microphone"
            >
              <Mic size={21} />
            </button>

            {/* SEND */}
            <button
              className="send-button"
              onClick={handleSend}
              aria-label="Send message"
              disabled={
                !message.trim() &&
                selectedFiles.length === 0
              }
            >
              <Send size={19} />
            </button>

          </div>

        </section>

      </main>

    </div>
  );
}

export default App;