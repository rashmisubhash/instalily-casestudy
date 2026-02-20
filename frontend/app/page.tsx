"use client";

import React from "react";
import { Container } from "react-bootstrap";
import Header from "@/app/components/layout/Header";
import WelcomeScreen from "@/app/components/chat/WelcomeScreen";
import Message from "@/app/components/chat/Message";
import TypingIndicator from "@/app/components/chat/TypingIndicator";
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

          {/* Messages Area */}
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

                {messages.map((msg) => (
                  <Message
                    key={msg.id}
                    id={msg.id}
                    role={msg.role}
                    content={msg.content}
                    payload={msg.payload}
                    type={msg.type}
                    confidence={msg.confidence}
                    timestamp={msg.timestamp}
                    onQuickAction={(text) => {
                      setInput(text);
                    }}
                  />
                ))}

                {searchQuery && filteredMessages.length === 0 && (
                  <div className="no-results">
                    No messages found for "{searchQuery}"
                  </div>
                )}

                {isLoading && <TypingIndicator />}
              </>
            )}
            <div ref={messagesEndRef} />
          </div>

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
