import { useState, useEffect, useRef } from "react";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content?: string;
  payload?: any;
  type?: string;
  confidence?: number;
  detectedModel?: string;
  timestamp: Date;
}

export function useChatLogic() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // ---------- Generate / Restore Conversation ID ----------
  useEffect(() => {
    const savedConversationId = localStorage.getItem("partselect-conversation-id");

    if (savedConversationId) {
      setConversationId(savedConversationId);
    } else {
      const newId = crypto.randomUUID();
      localStorage.setItem("partselect-conversation-id", newId);
      setConversationId(newId);
    }
  }, []);

  // ---------- Load Chat History ----------
  useEffect(() => {
    const savedMessages = localStorage.getItem("partselect-chat-history");
    if (savedMessages) {
      try {
        const parsed = JSON.parse(savedMessages);
        const messagesWithDates = parsed.map((msg: any) => ({
          ...msg,
          timestamp: new Date(msg.timestamp),
        }));
        setMessages(messagesWithDates);
      } catch (err) {
        console.error("Failed to load chat history:", err);
      }
    }
  }, []);

  // ---------- Persist Messages ----------
  useEffect(() => {
    if (messages.length > 0) {
      localStorage.setItem("partselect-chat-history", JSON.stringify(messages));
    }
  }, [messages]);

  // ---------- Auto Scroll ----------
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // ---------- Keyboard Shortcuts ----------
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        (e.ctrlKey || e.metaKey) &&
        e.key === "Enter" &&
        input.trim() &&
        !isLoading
      ) {
        e.preventDefault();
        const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
        handleSubmit(fakeEvent);
      }

      if (e.key === "Escape" && input) {
        setInput("");
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [input, isLoading]);

  // ---------- Submit Handler ----------
  const handleSubmit = async (e: React.FormEvent, retryCount = 0) => {
    e.preventDefault();
    if (!input.trim() || isLoading || !conversationId) return;

    const trimmed = input.trim();

    const isModel = /^[A-Z0-9]{6,15}$/.test(trimmed.toUpperCase());

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: trimmed,
      detectedModel: isModel ? trimmed : undefined,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000);

      const response = await fetch("http://localhost:8000/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          conversation_id: conversationId,
          message: trimmed,
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      const data = await response.json();

      // If backend generates conversation_id (first request), update it
      if (data.conversation_id && data.conversation_id !== conversationId) {
        setConversationId(data.conversation_id);
        localStorage.setItem("partselect-conversation-id", data.conversation_id);
      }

      const agent = data.response;

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: agent?.explanation || agent?.message || "",
        payload: agent,
        type: agent?.type,
        confidence: agent?.confidence,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);

    } catch (error) {
      console.error("Error:", error);

      if (
        retryCount < 2 &&
        error instanceof Error &&
        error.name !== "AbortError"
      ) {
        setTimeout(() => {
          const retryEvent = { preventDefault: () => {} } as React.FormEvent;
          handleSubmit(retryEvent, retryCount + 1);
        }, 1000);
        return;
      }

      let errorMessage = "Sorry, something went wrong. Please try again.";

      if (error instanceof Error) {
        if (error.name === "AbortError") {
          errorMessage = "Request timed out. Please try again.";
        } else if (error.message.includes("Failed to fetch")) {
          errorMessage =
            "Cannot connect to the server. Please check if the backend is running.";
        }
      }

      const assistantErrorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: errorMessage,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantErrorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  // ---------- Clear Chat ----------
  const clearChat = () => {
    setMessages([]);
    setInput("");
    setSearchQuery("");

    const newId = crypto.randomUUID();
    setConversationId(newId);

    localStorage.setItem("partselect-conversation-id", newId);
    localStorage.removeItem("partselect-chat-history");
  };

  // ---------- Export Chat ----------
  const exportChat = () => {
    if (messages.length === 0) return;

    const chatText = messages
      .map((msg) => {
        const time = msg.timestamp.toLocaleString();
        const role = msg.role === "user" ? "You" : "Assistant";
        return `[${time}] ${role}:\n${msg.content}\n`;
      })
      .join("\n");

    const blob = new Blob([chatText], { type: "text/plain" });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = `partselect-chat-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    URL.revokeObjectURL(url);
  };

  const filteredMessages = searchQuery
    ? messages.filter((msg) =>
        msg.content?.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : messages;

  return {
    messages,
    filteredMessages,
    input,
    isLoading,
    searchQuery,
    messagesEndRef,
    setInput,
    setSearchQuery,
    handleSubmit,
    clearChat,
    exportChat,
  };
}
