"use client";

import React from "react";
import { Container } from "react-bootstrap";
import Header from "@/app/components/layout/Header";
import WelcomeScreen from "@/app/components/chat/WelcomeScreen";
import Message from "@/app/components/chat/Message";
import TypingIndicator from "@/app/components/chat/TypingIndicator";
import LoadingSkeleton from "@/app/components/chat/LoadingSkeleton";
import ChatInput from "@/app/components/chat/ChatInput";
import SearchBar from "@/app/components/chat/SearchBar";
import { useChatLogic } from "@/app/components/chat/useChatLogic";
import QuickActions from "@/app/components/chat/QuickActions";

export default function ChatPage() {
  const {
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
  } = useChatLogic();

  const latestAssistantMessage = [...messages]
    .reverse()
    .find((msg) => msg.role === "assistant");

  const latestPayload = latestAssistantMessage?.payload;

  const activeModel = (() => {
    for (const msg of [...messages].reverse()) {
      if (msg.payload?.model_id) return String(msg.payload.model_id).toUpperCase();
      if (msg.detectedModel) return msg.detectedModel.toUpperCase();
    }
    return null;
  })();

  const activeAppliance = (() => {
    const fromPayload = latestPayload?.detected_info?.appliance || latestPayload?.appliance;
    if (fromPayload) return String(fromPayload);

    const symptom = String(latestPayload?.symptom || "").toLowerCase();
    if (symptom.includes("dishwasher")) return "dishwasher";
    if (symptom.includes("refrigerator") || symptom.includes("fridge")) return "refrigerator";
    return null;
  })();

  const showRecoveryBar =
    !!latestAssistantMessage?.content &&
    (
      latestAssistantMessage.content.toLowerCase().includes("something went wrong") ||
      latestAssistantMessage.content.toLowerCase().includes("cannot connect") ||
      latestAssistantMessage.content.toLowerCase().includes("request timed out")
    );

  return (
    <>
      <Header />

      <Container className="chat-container">
        <div className="chat-card">
          {/* Search Bar */}
          {messages.length > 0 && (
            <SearchBar
              searchQuery={searchQuery}
              onSearchChange={setSearchQuery}
              onClearSearch={() => setSearchQuery("")}
              resultCount={filteredMessages.length}
            />
          )}

          {(activeModel || activeAppliance) && (
            <div className="context-strip">
              <span className="context-label">Conversation Context</span>
              {activeModel && <span className="context-chip">Model: {activeModel}</span>}
              {activeAppliance && (
                <span className="context-chip">Appliance: {activeAppliance}</span>
              )}
            </div>
          )}

          {/* Messages Area */}
          <div className="messages-container">
            {messages.length === 0 ? (
              <WelcomeScreen onExampleClick={setInput} />
            ) : (
              <>
                {/* Quick Actions Bar - Always Visible */}
                <div className="chat-quick-actions-bar">
                  <QuickActions onActionClick={setInput} />
                </div>

                {filteredMessages.map((msg) => (
                  <Message
                    key={msg.id}
                    role={msg.role}
                    content={msg.content}
                    payload={msg.payload}
                    confidence={msg.confidence}
                    timestamp={msg.timestamp}
                    onQuickAction={setInput}
                  />
                ))}

                {searchQuery && filteredMessages.length === 0 && (
                  <div className="no-results">
                    No messages found for "{searchQuery}"
                  </div>
                )}

                {isLoading && (
                  <>
                    <TypingIndicator />
                    <LoadingSkeleton />
                  </>
                )}
              </>
            )}
            <div ref={messagesEndRef} />
          </div>

          {showRecoveryBar && (
            <div className="recovery-bar">
              <span>Need help getting back on track?</span>
              <button type="button" onClick={() => setInput("Please retry my previous request")}>
                Retry previous request
              </button>
              <button type="button" onClick={() => setInput("Help me find my appliance model number")}>
                Find my model number
              </button>
            </div>
          )}

          {/* Input Area */}
          <ChatInput
            input={input}
            isLoading={isLoading}
            hasMessages={messages.length > 0}
            onInputChange={setInput}
            onSubmit={handleSubmit}
            onClear={clearChat}
            onExport={exportChat}
          />
        </div>
      </Container>
    </>
  );
}
