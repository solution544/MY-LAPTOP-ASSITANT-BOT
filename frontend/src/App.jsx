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
  // ==========================================================
  // STATE
  // ==========================================================

  const [menuOpen, setMenuOpen] = useState(false);

  const [message, setMessage] = useState("");

  const [messages, setMessages] = useState([]);

  const [selectedFiles, setSelectedFiles] = useState([]);

  const [conversationId, setConversationId] = useState(null);

  const [conversations, setConversations] = useState([]);

  const [activePanel, setActivePanel] = useState(null);

  const [loadingConversations, setLoadingConversations] =
    useState(false);

  const [loadingConversation, setLoadingConversation] =
    useState(false);

  const [sending, setSending] = useState(false);

  const [error, setError] = useState("");

  const fileInputRef = useRef(null);

  // ==========================================================
  // VOICE
  // ==========================================================

  const {
    isListening,
    isProcessing,
    transcript,
    reply,
    toggleListening,
  } = useVoice();

  // ==========================================================
  // LOAD ALL CONVERSATIONS
  // ==========================================================

  const loadConversations = async () => {
    try {
      setLoadingConversations(true);
      setError("");

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
      console.error("Conversation loading error:", err);

      setError(
        "Unable to load conversations. Check that the backend is running."
      );

      setConversations([]);
    } finally {
      setLoadingConversations(false);
    }
  };

  // ==========================================================
  // LOAD A SINGLE CONVERSATION
  // ==========================================================

  const openConversation = async (id) => {
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

      setConversationId(data.id || id);

      const loadedMessages = Array.isArray(data.messages)
        ? data.messages
        : [];

      setMessages(
        loadedMessages
          .filter(
            (msg) =>
              msg.role === "user" ||
              msg.role === "assistant"
          )
          .map((msg) => ({
            role: msg.role,
            content: msg.content || "",
          }))
      );

      setSelectedFiles([]);
      setMessage("");

      // Close everything after opening a conversation
      setActivePanel(null);
      setMenuOpen(false);
    } catch (err) {
      console.error("Open conversation error:", err);

      setError(
        "Unable to open this conversation."
      );
    } finally {
      setLoadingConversation(false);
    }
  };

  // ==========================================================
  // NEW CONVERSATION
  // ==========================================================

  const handleNewConversation = () => {
    setConversationId(null);
    setMessages([]);
    setMessage("");
    setSelectedFiles([]);
    setActivePanel(null);
    setMenuOpen(false);
    setError("");

    // Clear file input as well
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // ==========================================================
  // CONVERSATIONS PANEL
  // ==========================================================

  const handleConversations = async () => {
    setMenuOpen(false);
    setActivePanel("conversations");

    await loadConversations();
  };

  // ==========================================================
  // HISTORY PANEL
  // ==========================================================

  const handleHistory = async () => {
    setMenuOpen(false);
    setActivePanel("history");

    await loadConversations();
  };

  // ==========================================================
  // SETTINGS PANEL
  // ==========================================================

  const handleSettings = () => {
    setMenuOpen(false);
    setActivePanel("settings");
    setError("");
  };

  // ==========================================================
  // CLOSE PANEL
  // ==========================================================

  const closePanel = () => {
    setActivePanel(null);
  };

  // ==========================================================
  // SPACEBAR → VOICE
  // ==========================================================

  useEffect(() => {
    const handleVoiceShortcut = (event) => {
      const target = event.target;

      const isTyping =
        target?.tagName === "INPUT" ||
        target?.tagName === "TEXTAREA" ||
        target?.isContentEditable;

      if (
        event.code === "Space" &&
        !isTyping
      ) {
        event.preventDefault();
        toggleListening();
      }
    };

    window.addEventListener(
      "keydown",
      handleVoiceShortcut
    );

    return () => {
      window.removeEventListener(
        "keydown",
        handleVoiceShortcut
      );
    };
  }, [toggleListening]);

  // ==========================================================
  // SEND MESSAGE + FILES
  // ==========================================================

  const handleSend = async () => {
    const trimmedMessage = message.trim();

    if (
      !trimmedMessage &&
      selectedFiles.length === 0
    ) {
      return;
    }

    if (sending) {
      return;
    }

    const filesToSend = [...selectedFiles];

    // ========================================================
    // SHOW USER MESSAGE IMMEDIATELY
    // ========================================================

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
      // ======================================================
      // FORM DATA
      // ======================================================

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

      /*
       * Backend currently accepts one `file`.
       *
       * Therefore send the first selected file.
       */
      if (filesToSend.length > 0) {
        formData.append(
          "file",
          filesToSend[0]
        );
      }

      // ======================================================
      // API REQUEST
      // ======================================================

      const response = await fetch(
        `${API_BASE_URL}/api/chat`,
        {
          method: "POST",
          body: formData,
        }
      );

      if (!response.ok) {
        let errorMessage =
          "Failed to send message.";

        try {
          const errorData =
            await response.json();

          if (errorData?.detail) {
            errorMessage =
              typeof errorData.detail === "string"
                ? errorData.detail
                : JSON.stringify(
                    errorData.detail
                  );
          }
        } catch {
          const text =
            await response.text();

          if (text) {
            errorMessage = text;
          }
        }

        throw new Error(errorMessage);
      }

      const data =
        await response.json();

      // ======================================================
      // STORE CONVERSATION ID
      // ======================================================

      if (data.conversation_id) {
        setConversationId(
          data.conversation_id
        );
      }

      // ======================================================
      // ASSISTANT RESPONSE
      // ======================================================

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",

          content:
            data.content ||
            "I completed the request.",

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
            data.permission_level ||
            null,
        },
      ]);

      // ======================================================
      // REFRESH CONVERSATIONS
      // ======================================================

      await loadConversations();
    } catch (err) {
      console.error("Chat error:", err);

      setError(
        err.message ||
          "Something went wrong while contacting Solution AI."
      );

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            `Sorry, I couldn't process your request.\n\n${
              err.message ||
              "Unknown error"
            }`,
        },
      ]);
    } finally {
      setSending(false);
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
      setError("");

      const response = await fetch(
        `${API_BASE_URL}/api/chat/confirm`,
        {
          method: "POST",

          headers: {
            "Content-Type":
              "application/json",
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
          "Confirmation request failed.";

        try {
          const errorData =
            await response.json();

          if (errorData?.detail) {
            errorMessage =
              typeof errorData.detail === "string"
                ? errorData.detail
                : JSON.stringify(
                    errorData.detail
                  );
          }
        } catch {
          const text =
            await response.text();

          if (text) {
            errorMessage = text;
          }
        }

        throw new Error(errorMessage);
      }

      const data =
        await response.json();

      // Remove confirmation buttons
      setMessages((prev) =>
        prev.map((msg) =>
          msg.confirmation_id ===
          confirmationId
            ? {
                ...msg,
                confirmation_required:
                  false,
              }
            : msg
        )
      );

      // Add result message
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

      await loadConversations();
    } catch (err) {
      console.error(
        "Chat confirmation error:",
        err
      );

      setError(
        err.message ||
          "I couldn't process that confirmation."
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

      if (!sending) {
        handleSend();
      }
    }
  };

  // ==========================================================
  // FILE SELECTION
  // ==========================================================

  const handleFileChange = (event) => {
    const files = Array.from(
      event.target.files || []
    );

    if (files.length === 0) {
      return;
    }

    setSelectedFiles((prev) => {
      const existingKeys = new Set(
        prev.map(
          (file) =>
            `${file.name}-${file.size}-${file.lastModified}`
        )
      );

      const newFiles = files.filter(
        (file) =>
          !existingKeys.has(
            `${file.name}-${file.size}-${file.lastModified}`
          )
      );

      return [...prev, ...newFiles];
    });

    // Allow selecting the same file again later
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
  // RENDER
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
            setMenuOpen((prev) => !prev)
          }
          aria-label="Open menu"
          type="button"
        >
          <Menu size={24} />
        </button>

        <div className="logo">
          <span className="logo-dot"></span>
          SOLUTION AI
        </div>

        <button
          className="icon-button"
          onClick={handleSettings}
          aria-label="Settings"
          type="button"
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

        {/* NEW CONVERSATION */}

        <button
          className="new-chat"
          onClick={
            handleNewConversation
          }
          type="button"
        >
          <Plus size={17} />
          New Conversation
        </button>

        {/* NAVIGATION */}

        <nav>

          <button
            onClick={
              handleConversations
            }
            type="button"
          >
            <MessageSquare size={17} />
            Conversations
          </button>

          <button
            onClick={handleHistory}
            type="button"
          >
            <HistoryIcon size={17} />
            History
          </button>

          <button
            onClick={handleSettings}
            type="button"
          >
            <Settings size={17} />
            Settings
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

          <div className="voice-status">

            <span
              className={`status-dot ${
                isListening
                  ? "active"
                  : ""
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

          {transcript && (
            <div className="transcript">

              <span>You:</span>

              <p>{transcript}</p>

            </div>
          )}

          {reply && (
            <div className="transcript">

              <span>
                Solution AI:
              </span>

              <p>{reply}</p>

            </div>
          )}

        </section>

        {/* ==================================================
            ERROR
        ================================================== */}

        {error && (
          <div className="error-message">

            <span>{error}</span>

            <button
              type="button"
              onClick={() =>
                setError("")
              }
              aria-label="Close error"
            >
              <X size={16} />
            </button>

          </div>
        )}

        {/* ==================================================
            PANELS
        ================================================== */}

        {activePanel && (
          <section className="side-panel">

            {/* PANEL HEADER */}

            <div className="side-panel-header">

              <h2>
                {activePanel ===
                  "conversations" &&
                  "Conversations"}

                {activePanel ===
                  "history" &&
                  "History"}

                {activePanel ===
                  "settings" &&
                  "Settings"}
              </h2>

              <button
                type="button"
                onClick={closePanel}
                aria-label="Close panel"
              >
                <X size={20} />
              </button>

            </div>

            {/* =================================================
                CONVERSATIONS / HISTORY
            ================================================= */}

            {(activePanel ===
              "conversations" ||
              activePanel ===
                "history") && (

              <div className="conversation-list">

                {/* NEW CHAT */}

                <button
                  className="panel-new-chat"
                  onClick={
                    handleNewConversation
                  }
                  type="button"
                >
                  <Plus size={17} />
                  New Conversation
                </button>

                {/* LOADING */}

                {loadingConversations && (
                  <div className="panel-empty">
                    Loading conversations...
                  </div>
                )}

                {/* LOADING SINGLE CONVERSATION */}

                {loadingConversation && (
                  <div className="panel-empty">
                    Opening conversation...
                  </div>
                )}

                {/* EMPTY */}

                {!loadingConversations &&
                  conversations.length ===
                    0 && (
                    <div className="panel-empty">
                      No conversations yet.
                    </div>
                  )}

                {/* CONVERSATION LIST */}

                {!loadingConversations &&
                  conversations.length >
                    0 && (
                    <div className="conversation-items">

                      {conversations.map(
                        (conversation) => (
                          <button
                            className={`conversation-item ${
                              conversation.id ===
                              conversationId
                                ? "active"
                                : ""
                            }`}
                            key={
                              conversation.id
                            }
                            onClick={() =>
                              openConversation(
                                conversation.id
                              )
                            }
                            type="button"
                          >

                            <MessageSquare
                              size={17}
                            />

                            <div>

                              <strong>
                                {conversation.title ||
                                  "Untitled Conversation"}
                              </strong>

                              <small>
                                {conversation.updated_at
                                  ? new Date(
                                      conversation.updated_at
                                    ).toLocaleString()
                                  : ""}
                              </small>

                            </div>

                          </button>
                        )
                      )}

                    </div>
                  )}

                {/* REFRESH */}

                <button
                  className="refresh-button"
                  onClick={
                    loadConversations
                  }
                  disabled={
                    loadingConversations
                  }
                  type="button"
                >

                  <RefreshCw
                    size={16}
                    className={
                      loadingConversations
                        ? "spin"
                        : ""
                    }
                  />

                  {loadingConversations
                    ? "Refreshing..."
                    : "Refresh"}

                </button>

              </div>
            )}

            {/* =================================================
                SETTINGS
            ================================================= */}

            {activePanel ===
              "settings" && (

              <div className="settings-panel">

                <div className="setting-item">

                  <strong>
                    Backend
                  </strong>

                  <span>
                    {API_BASE_URL}
                  </span>

                </div>

                <div className="setting-item">

                  <strong>
                    AI Status
                  </strong>

                  <span>
                    Solution AI backend
                  </span>

                </div>

                <div className="setting-item">

                  <strong>
                    Voice
                  </strong>

                  <span>
                    {isListening
                      ? "Listening"
                      : isProcessing
                      ? "Processing"
                      : "Ready"}
                  </span>

                </div>

                <div className="setting-item">

                  <strong>
                    Current Conversation
                  </strong>

                  <span>
                    {conversationId
                      ? conversationId
                      : "New conversation"}
                  </span>

                </div>

              </div>
            )}

          </section>
        )}

        {/* ==================================================
            CHAT
        ================================================== */}

        <section className="chat-area">

          <div className="chat-messages">

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
                            filename,
                            fileIndex
                          ) => (

                            <div
                              className="message-file"
                              key={`${filename}-${fileIndex}`}
                            >
                              📎{" "}
                              {filename}
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

                    <div className="confirmation-buttons">

                      <button
                        className="confirmation-yes"
                        onClick={() =>
                          handleConfirmation(
                            msg.confirmation_id,
                            true
                          )
                        }
                        type="button"
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
                        type="button"
                      >
                        ✕ No
                      </button>

                    </div>
                  )}

                </div>
              )
            )}

            {/* SENDING */}

            {sending && (
              <div className="chat-message assistant">

                <span>
                  Solution AI
                </span>

                <p>
                  {selectedFiles.length > 0
                    ? "Reading your file and thinking..."
                    : "Thinking..."}
                </p>

              </div>
            )}

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
                    key={`${file.name}-${file.size}-${index}`}
                  >

                    <span>
                      📎 {file.name}
                    </span>

                    <button
                      type="button"
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

            {/* FILE BUTTON */}

            <button
              className="chat-icon-button"
              onClick={() =>
                fileInputRef.current?.click()
              }
              aria-label="Attach file"
              type="button"
              disabled={sending}
            >
              <Paperclip size={21} />
            </button>

            {/* FILE INPUT */}

            <input
              ref={fileInputRef}
              type="file"
              multiple
              hidden
              onChange={
                handleFileChange
              }
              accept=".txt,.md,.pdf,.docx,.csv,.json,.xml,.yaml,.yml,.py,.js,.jsx,.ts,.tsx,.css,.html,.htm,.sql"
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
              onKeyDown={
                handleKeyDown
              }
              placeholder={
                selectedFiles.length > 0
                  ? "Ask Solution AI about your file..."
                  : "Type a message..."
              }
              autoComplete="off"
              disabled={sending}
            />

            {/* MICROPHONE */}

            <button
              className={
                isListening
                  ? "chat-icon-button mic-active"
                  : "chat-icon-button"
              }
              onClick={
                toggleListening
              }
              aria-label="Activate microphone"
              type="button"
              disabled={sending}
            >
              <Mic size={21} />
            </button>

            {/* SEND */}

            <button
              className="send-button"
              onClick={
                handleSend
              }
              aria-label="Send message"
              type="button"
              disabled={
                sending ||
                (!message.trim() &&
                  selectedFiles.length ===
                    0)
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