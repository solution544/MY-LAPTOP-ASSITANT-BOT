import { useEffect, useRef, useState } from "react";
import {
  Menu,
  Settings,
  Mic,
  Paperclip,
  Send,
  X,
  MessageSquare,
  History as HistoryIcon,
  Plus,
  RefreshCw,
} from "lucide-react";
import useVoice from "./hooks/useVoice";
import "./App.css";

const API_BASE_URL =
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([]);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [conversationId, setConversationId] = useState(null);

  const [conversations, setConversations] = useState([]);
  const [activePanel, setActivePanel] = useState("chat");

  const [loadingConversations, setLoadingConversations] = useState(false);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  const fileInputRef = useRef(null);
  const textareaRef = useRef(null);

  const {
    isListening,
    transcript,
    startListening,
    stopListening,
    supported: voiceSupported,
  } = useVoice();

  // --------------------------------------------------
  // LOAD CONVERSATIONS
  // --------------------------------------------------

  const loadConversations = async () => {
    try {
      setLoadingConversations(true);

      const response = await fetch(
        `${API_BASE_URL}/api/conversations`
      );

      if (!response.ok) {
        throw new Error(
          `Failed to load conversations (${response.status})`
        );
      }

      const data = await response.json();

      setConversations(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error("Failed to load conversations:", err);
    } finally {
      setLoadingConversations(false);
    }
  };

  // --------------------------------------------------
  // LOAD SINGLE CONVERSATION
  // --------------------------------------------------

  const loadConversation = async (id) => {
    if (!id) return;

    try {
      setLoadingConversation(true);
      setError("");

      const response = await fetch(
        `${API_BASE_URL}/api/conversations/${id}`
      );

      if (!response.ok) {
        throw new Error(
          `Failed to load conversation (${response.status})`
        );
      }

      const data = await response.json();

      setConversationId(data.id);

      setMessages(
        Array.isArray(data.messages)
          ? data.messages.map((msg) => ({
              role: msg.role,
              content: msg.content || "",
            }))
          : []
      );

      setActivePanel("chat");
      setMenuOpen(false);
    } catch (err) {
      console.error("Failed to load conversation:", err);
      setError(err.message);
    } finally {
      setLoadingConversation(false);
    }
  };

  // --------------------------------------------------
  // NEW CONVERSATION
  // --------------------------------------------------

  const startNewConversation = () => {
    setConversationId(null);
    setMessages([]);
    setMessage("");
    setSelectedFiles([]);
    setError("");
    setActivePanel("chat");
    setMenuOpen(false);

    setTimeout(() => {
      textareaRef.current?.focus();
    }, 50);
  };

  // --------------------------------------------------
  // INITIAL LOAD
  // --------------------------------------------------

  useEffect(() => {
    loadConversations();
  }, []);

  // --------------------------------------------------
  // VOICE TRANSCRIPT
  // --------------------------------------------------

  useEffect(() => {
    if (transcript) {
      setMessage((prev) => {
        const separator = prev.trim() ? " " : "";
        return `${prev}${separator}${transcript}`;
      });
    }
  }, [transcript]);

  // --------------------------------------------------
  // SPACEBAR VOICE SHORTCUT
  // --------------------------------------------------

  useEffect(() => {
    const handleKeyDown = (event) => {
      const target = event.target;

      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target?.isContentEditable
      ) {
        return;
      }

      if (
        event.code === "Space" &&
        !event.repeat &&
        voiceSupported
      ) {
        event.preventDefault();
        startListening();
      }
    };

    const handleKeyUp = (event) => {
      if (
        event.code === "Space" &&
        voiceSupported
      ) {
        event.preventDefault();
        stopListening();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
    };
  }, [
    voiceSupported,
    startListening,
    stopListening,
  ]);

  // --------------------------------------------------
  // FILE SELECTION
  // --------------------------------------------------

  const handleFileChange = (event) => {
    const files = Array.from(event.target.files || []);

    if (!files.length) return;

    setSelectedFiles((prev) => {
      const existingNames = new Set(
        prev.map((file) => `${file.name}-${file.size}`)
      );

      const newFiles = files.filter(
        (file) =>
          !existingNames.has(
            `${file.name}-${file.size}`
          )
      );

      return [...prev, ...newFiles];
    });

    event.target.value = "";
  };

  const removeSelectedFile = (index) => {
    setSelectedFiles((prev) =>
      prev.filter((_, i) => i !== index)
    );
  };

  // --------------------------------------------------
  // SEND MESSAGE
  // --------------------------------------------------

  const handleSend = async () => {
    const trimmedMessage = message.trim();

    if (
      !trimmedMessage &&
      selectedFiles.length === 0
    ) {
      return;
    }

    if (sending) return;

    const filesToSend = [...selectedFiles];

    // Immediately display user's message
    setMessages((prev) => [
      ...prev,
      {
        role: "user",
        content:
          trimmedMessage ||
          "Please analyze the uploaded file.",
        files: filesToSend.map(
          (file) => file.name
        ),
      },
    ]);

    setMessage("");
    setSelectedFiles([]);
    setSending(true);
    setError("");

    try {
      const formData = new FormData();

      formData.append(
        "message",
        trimmedMessage
      );

      if (conversationId) {
        formData.append(
          "conversation_id",
          conversationId
        );
      }

      // Backend currently accepts one file.
      if (filesToSend.length > 0) {
        formData.append(
          "file",
          filesToSend[0]
        );
      }

      console.log(
        "Sending message to Solution AI..."
      );

      const response = await fetch(
        `${API_BASE_URL}/api/chat`,
        {
          method: "POST",
          body: formData,
        }
      );

      console.log(
        "Solution AI API status:",
        response.status
      );

      if (!response.ok) {
        let errorMessage =
          `Backend returned HTTP ${response.status}.`;

        try {
          const errorData =
            await response.json();

          console.error(
            "Solution AI API error:",
            errorData
          );

          if (errorData?.detail) {
            errorMessage =
              typeof errorData.detail ===
              "string"
                ? errorData.detail
                : JSON.stringify(
                    errorData.detail
                  );
          }
        } catch {
          // Ignore JSON parsing failure
        }

        throw new Error(errorMessage);
      }

      const data = await response.json();

      console.log(
        "Solution AI API response:",
        data
      );

      console.log(
        "Solution AI content:",
        data?.content
      );

      // Save conversation ID
      if (data?.conversation_id) {
        setConversationId(
          data.conversation_id
        );
      }

      const assistantContent =
        typeof data?.content === "string"
          ? data.content.trim()
          : "";

      if (!assistantContent) {
        console.error(
          "Backend returned no assistant content:",
          data
        );

        throw new Error(
          "The backend responded successfully, but no AI message was returned."
        );
      }

      // THIS IS THE IMPORTANT PART:
      // Add the actual backend response to the UI.
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: assistantContent,

          confirmation_required:
            Boolean(
              data.confirmation_required
            ),

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

      // Refresh sidebar
      await loadConversations();
    } catch (err) {
      console.error(
        "Solution AI chat error:",
        err
      );

      const errorMessage =
        err?.message ||
        "Something went wrong while contacting Solution AI.";

      setError(errorMessage);

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            `Sorry, I couldn't process your request.\n\n${errorMessage}`,
        },
      ]);
    } finally {
      setSending(false);
    }
  };

  // --------------------------------------------------
  // ENTER TO SEND
  // --------------------------------------------------

  const handleTextareaKeyDown = (event) => {
    if (
      event.key === "Enter" &&
      !event.shiftKey
    ) {
      event.preventDefault();
      handleSend();
    }
  };

  // --------------------------------------------------
  // CONFIRMATION
  // --------------------------------------------------

  const handleConfirmation = async (
    confirmationId,
    approved
  ) => {
    if (!confirmationId) return;

    try {
      setSending(true);
      setError("");

      const response = await fetch(
        `${API_BASE_URL}/api/chat/confirm`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            confirmation_id:
              confirmationId,
            approved,
          }),
        }
      );

      if (!response.ok) {
        let errorMessage =
          `Confirmation failed (${response.status}).`;

        try {
          const errorData =
            await response.json();

          if (errorData?.detail) {
            errorMessage =
              typeof errorData.detail ===
              "string"
                ? errorData.detail
                : JSON.stringify(
                    errorData.detail
                  );
          }
        } catch {
          // Ignore
        }

        throw new Error(errorMessage);
      }

      const data = await response.json();

      console.log(
        "Confirmation response:",
        data
      );

      const assistantContent =
        typeof data?.content === "string"
          ? data.content.trim()
          : "";

      if (assistantContent) {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: assistantContent,
          },
        ]);
      }

      if (data?.conversation_id) {
        setConversationId(
          data.conversation_id
        );
      }

      await loadConversations();
    } catch (err) {
      console.error(
        "Confirmation error:",
        err
      );

      setError(
        err?.message ||
          "Failed to process confirmation."
      );
    } finally {
      setSending(false);
    }
  };

  // --------------------------------------------------
  // MENU
  // --------------------------------------------------

  const openPanel = (panel) => {
    setActivePanel(panel);
    setMenuOpen(false);
  };

  // --------------------------------------------------
  // RENDER
  // --------------------------------------------------

  return (
    <div className="app">

      {/* SIDEBAR OVERLAY */}
      {menuOpen && (
        <div
          className="sidebar-overlay"
          onClick={() => setMenuOpen(false)}
        />
      )}

      {/* SIDEBAR */}
      <aside
        className={`sidebar ${
          menuOpen ? "open" : ""
        }`}
      >
        <div className="sidebar-header">
          <div className="brand">
            <div className="brand-icon">
              S
            </div>

            <div>
              <h2>Solution AI</h2>
              <span>AI Assistant</span>
            </div>
          </div>

          <button
            className="icon-button"
            onClick={() =>
              setMenuOpen(false)
            }
          >
            <X size={20} />
          </button>
        </div>

        <button
          className="new-chat-button"
          onClick={startNewConversation}
        >
          <Plus size={19} />
          New Chat
        </button>

        <nav className="sidebar-nav">
          <button
            className={
              activePanel === "chat"
                ? "nav-item active"
                : "nav-item"
            }
            onClick={() =>
              openPanel("chat")
            }
          >
            <MessageSquare size={19} />
            Chat
          </button>

          <button
            className={
              activePanel === "history"
                ? "nav-item active"
                : "nav-item"
            }
            onClick={() =>
              openPanel("history")
            }
          >
            <HistoryIcon size={19} />
            History
          </button>

          <button
            className={
              activePanel === "settings"
                ? "nav-item active"
                : "nav-item"
            }
            onClick={() =>
              openPanel("settings")
            }
          >
            <Settings size={19} />
            Settings
          </button>
        </nav>

        <div className="sidebar-section">
          <div className="sidebar-section-title">
            Recent conversations
          </div>

          {loadingConversations ? (
            <div className="sidebar-loading">
              Loading...
            </div>
          ) : conversations.length === 0 ? (
            <div className="sidebar-empty">
              No conversations yet.
            </div>
          ) : (
            <div className="conversation-list">
              {conversations.map(
                (conversation) => (
                  <button
                    key={conversation.id}
                    className={`conversation-item ${
                      conversationId ===
                      conversation.id
                        ? "active"
                        : ""
                    }`}
                    onClick={() =>
                      loadConversation(
                        conversation.id
                      )
                    }
                  >
                    <MessageSquare
                      size={16}
                    />

                    <span>
                      {conversation.title ||
                        "New conversation"}
                    </span>
                  </button>
                )
              )}
            </div>
          )}
        </div>
      </aside>

      {/* MAIN */}
      <main className="main">

        {/* HEADER */}
        <header className="topbar">
          <button
            className="icon-button menu-button"
            onClick={() =>
              setMenuOpen(true)
            }
          >
            <Menu size={22} />
          </button>

          <div className="topbar-title">
            <h1>Solution AI</h1>
            <span>
              {activePanel === "chat"
                ? "Your AI computer assistant"
                : activePanel ===
                  "history"
                ? "Conversation history"
                : "Settings"}
            </span>
          </div>

          <button
            className="icon-button"
            onClick={() =>
              loadConversations()
            }
            title="Refresh conversations"
          >
            <RefreshCw
              size={19}
              className={
                loadingConversations
                  ? "spin"
                  : ""
              }
            />
          </button>
        </header>

        {/* CONTENT */}
        <div className="content">

          {/* CHAT */}
          {activePanel === "chat" && (
            <div className="chat-container">

              <div className="chat-messages">

                {loadingConversation && (
                  <div className="chat-message assistant">
                    <span>
                      Solution AI
                    </span>
                    <p>
                      Loading conversation...
                    </p>
                  </div>
                )}

                {messages.length === 0 &&
                  !loadingConversation && (
                    <div className="welcome">
                      <div className="welcome-icon">
                        S
                      </div>

                      <h2>
                        Welcome to Solution AI
                      </h2>

                      <p>
                        Your AI assistant for
                        chatting, computer
                        control, files, web
                        search, and more.
                      </p>

                      <div className="suggestions">
                        <button
                          onClick={() =>
                            setMessage(
                              "What can you do?"
                            )
                          }
                        >
                          What can you do?
                        </button>

                        <button
                          onClick={() =>
                            setMessage(
                              "What is my computer screen size?"
                            )
                          }
                        >
                          Check my screen size
                        </button>

                        <button
                          onClick={() =>
                            setMessage(
                              "Take a screenshot of my screen and tell me what you see."
                            )
                          }
                        >
                          Analyze my screen
                        </button>
                      </div>
                    </div>
                  )}

                {messages.map(
                  (msg, index) => (
                    <div
                      key={`${msg.role}-${index}`}
                      className={`chat-message ${msg.role}`}
                    >
                      <span>
                        {msg.role ===
                        "user"
                          ? "You"
                          : "Solution AI"}
                      </span>

                      {/* FILES */}
                      {msg.files &&
                        msg.files.length >
                          0 && (
                          <div className="message-files">
                            {msg.files.map(
                              (
                                fileName,
                                fileIndex
                              ) => (
                                <div
                                  className="message-file"
                                  key={
                                    `${fileName}-${fileIndex}`
                                  }
                                >
                                  📎{" "}
                                  {fileName}
                                </div>
                              )
                            )}
                          </div>
                        )}

                      {/* MESSAGE */}
                      <p>
                        {msg.content}
                      </p>

                      {/* CONFIRMATION */}
                      {msg.confirmation_required &&
                        msg.confirmation_id && (
                          <div className="confirmation-box">

                            <div className="confirmation-text">
                              {msg.description ||
                                "This action requires your confirmation."}
                            </div>

                            <div className="confirmation-buttons">

                              <button
                                className="confirm-button"
                                onClick={() =>
                                  handleConfirmation(
                                    msg.confirmation_id,
                                    true
                                  )
                                }
                                disabled={sending}
                              >
                                Allow
                              </button>

                              <button
                                className="deny-button"
                                onClick={() =>
                                  handleConfirmation(
                                    msg.confirmation_id,
                                    false
                                  )
                                }
                                disabled={sending}
                              >
                                Deny
                              </button>

                            </div>
                          </div>
                        )}
                    </div>
                  )
                )}

                {/* THINKING */}
                {sending && (
                  <div className="chat-message assistant">
                    <span>
                      Solution AI
                    </span>

                    <p className="thinking">
                      Thinking...
                    </p>
                  </div>
                )}

              </div>

              {/* ERROR */}
              {error && (
                <div className="error-message">
                  {error}
                </div>
              )}

              {/* SELECTED FILES */}
              {selectedFiles.length >
                0 && (
                <div className="selected-files">
                  {selectedFiles.map(
                    (file, index) => (
                      <div
                        className="selected-file"
                        key={`${file.name}-${file.size}-${index}`}
                      >
                        <span>
                          📎 {file.name}
                        </span>

                        <button
                          onClick={() =>
                            removeSelectedFile(
                              index
                            )
                          }
                        >
                          <X size={15} />
                        </button>
                      </div>
                    )
                  )}
                </div>
              )}

              {/* INPUT */}
              <div className="input-area">

                <button
                  className="input-button"
                  title="Attach file"
                  onClick={() =>
                    fileInputRef.current?.click()
                  }
                >
                  <Paperclip size={20} />
                </button>

                <input
                  ref={fileInputRef}
                  type="file"
                  hidden
                  multiple
                  accept="
                    .txt,
                    .md,
                    .py,
                    .js,
                    .jsx,
                    .ts,
                    .tsx,
                    .css,
                    .html,
                    .htm,
                    .sql,
                    .json,
                    .xml,
                    .yaml,
                    .yml,
                    .log,
                    .env,
                    .csv,
                    .pdf,
                    .docx
                  "
                  onChange={
                    handleFileChange
                  }
                />

                <textarea
                  ref={textareaRef}
                  value={message}
                  onChange={(event) =>
                    setMessage(
                      event.target.value
                    )
                  }
                  onKeyDown={
                    handleTextareaKeyDown
                  }
                  placeholder={
                    isListening
                      ? "Listening..."
                      : "Message Solution AI..."
                  }
                  rows={1}
                />

                {voiceSupported && (
                  <button
                    className={`input-button voice-button ${
                      isListening
                        ? "listening"
                        : ""
                    }`}
                    title={
                      isListening
                        ? "Stop listening"
                        : "Voice input"
                    }
                    onClick={() => {
                      if (isListening) {
                        stopListening();
                      } else {
                        startListening();
                      }
                    }}
                  >
                    <Mic size={20} />
                  </button>
                )}

                <button
                  className="send-button"
                  onClick={handleSend}
                  disabled={
                    sending ||
                    (!message.trim() &&
                      selectedFiles.length ===
                        0)
                  }
                  title="Send message"
                >
                  <Send size={19} />
                </button>

              </div>

              <div className="input-hint">
                Press Enter to send • Shift +
                Enter for a new line
              </div>

            </div>
          )}

          {/* HISTORY */}
          {activePanel === "history" && (
            <div className="panel">

              <div className="panel-header">
                <div>
                  <h2>
                    Conversation History
                  </h2>

                  <p>
                    Your previous Solution AI
                    conversations.
                  </p>
                </div>

                <button
                  className="refresh-button"
                  onClick={
                    loadConversations
                  }
                >
                  <RefreshCw size={17} />
                  Refresh
                </button>
              </div>

              {loadingConversations ? (
                <div className="panel-empty">
                  Loading conversations...
                </div>
              ) : conversations.length ===
                0 ? (
                <div className="panel-empty">
                  <MessageSquare size={40} />

                  <h3>
                    No conversations
                  </h3>

                  <p>
                    Start a new chat to see it
                    here.
                  </p>
                </div>
              ) : (
                <div className="history-list">
                  {conversations.map(
                    (conversation) => (
                      <button
                        className="history-item"
                        key={conversation.id}
                        onClick={() =>
                          loadConversation(
                            conversation.id
                          )
                        }
                      >
                        <MessageSquare
                          size={19}
                        />

                        <div>
                          <strong>
                            {conversation.title ||
                              "New conversation"}
                          </strong>

                          <span>
                            {conversation.updated_at
                              ? new Date(
                                  conversation.updated_at
                                ).toLocaleString()
                              : ""}
                          </span>
                        </div>
                      </button>
                    )
                  )}
                </div>
              )}

            </div>
          )}

          {/* SETTINGS */}
          {activePanel === "settings" && (
            <div className="panel">

              <div className="panel-header">
                <div>
                  <h2>Settings</h2>

                  <p>
                    Configure your Solution AI
                    experience.
                  </p>
                </div>
              </div>

              <div className="settings-card">

                <div className="setting-row">
                  <div>
                    <strong>
                      AI Assistant
                    </strong>

                    <span>
                      Solution AI backend
                    </span>
                  </div>

                  <div className="status-badge">
                    Connected
                  </div>
                </div>

                <div className="setting-row">
                  <div>
                    <strong>
                      Voice Input
                    </strong>

                    <span>
                      Use your microphone to talk
                      to Solution AI.
                    </span>
                  </div>

                  <div className="status-badge">
                    {voiceSupported
                      ? "Available"
                      : "Unavailable"}
                  </div>
                </div>

                <div className="setting-row">
                  <div>
                    <strong>
                      Backend
                    </strong>

                    <span>
                      {API_BASE_URL}
                    </span>
                  </div>
                </div>

              </div>
            </div>
          )}

        </div>
      </main>
    </div>
  );
}

export default App;