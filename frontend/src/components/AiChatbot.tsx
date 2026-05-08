'use client';
// ==========================================
// 🤖 SAVIA AI Chatbot — Assistant conversationnel flottant
// ==========================================
import { useState, useRef, useEffect, useCallback } from 'react';
import { MessageSquare, X, Send, Loader2, Sparkles, RotateCcw, Bot, User } from 'lucide-react';
import { ai } from '@/lib/api';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  suggestions?: string[];
  timestamp: Date;
}

const WELCOME_MSG: ChatMessage = {
  role: 'assistant',
  content: "Bonjour ! Je suis l'assistant IA SAVIA. Je peux vous aider à analyser vos données de maintenance, équipements, interventions, et plus encore.\n\nPosez-moi une question !",
  suggestions: [
    "Combien d'interventions ce mois-ci ?",
    "Quels équipements tombent le plus en panne ?",
    "Quelles pièces sont en rupture de stock ?"
  ],
  timestamp: new Date(),
};

export default function AiChatbot() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MSG]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [pulse, setPulse] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  useEffect(() => {
    if (isOpen && inputRef.current) inputRef.current.focus();
  }, [isOpen]);

  // Stop pulse after first open
  useEffect(() => {
    if (isOpen) setPulse(false);
  }, [isOpen]);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || isLoading) return;
    const userMsg: ChatMessage = { role: 'user', content: text.trim(), timestamp: new Date() };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    // Build history for context (exclude welcome)
    const history = [...messages.filter(m => m !== WELCOME_MSG), userMsg].map(m => ({
      role: m.role, content: m.content
    }));

    try {
      const data = await ai.chat(text.trim(), history);
      const aiMsg: ChatMessage = {
        role: 'assistant',
        content: data.response,
        suggestions: data.suggestions,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, aiMsg]);
    } catch (err: any) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `❌ Erreur: ${err.message || "L'IA n'est pas disponible pour le moment."}`,
        timestamp: new Date(),
      }]);
    } finally {
      setIsLoading(false);
    }
  }, [isLoading, messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  const resetChat = () => {
    setMessages([WELCOME_MSG]);
    setInput('');
  };

  return (
    <>
      {/* ── Floating Bubble ── */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-gradient-to-br from-teal-500 to-cyan-600 text-white shadow-lg shadow-teal-500/30 flex items-center justify-center hover:scale-110 active:scale-95 transition-all duration-300 cursor-pointer group"
          aria-label="Ouvrir l'assistant IA"
        >
          <Sparkles className="w-6 h-6 group-hover:rotate-12 transition-transform" />
          {pulse && (
            <span className="absolute inset-0 rounded-full bg-teal-400 animate-ping opacity-30" />
          )}
        </button>
      )}

      {/* ── Chat Panel ── */}
      {isOpen && (
        <div className="fixed bottom-6 right-6 z-50 w-[400px] max-w-[calc(100vw-2rem)] h-[600px] max-h-[calc(100vh-4rem)] flex flex-col rounded-2xl border border-white/10 shadow-2xl shadow-black/40 overflow-hidden"
          style={{ background: 'rgba(15, 23, 42, 0.95)', backdropFilter: 'blur(20px)' }}>

          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 bg-gradient-to-r from-teal-600/20 to-cyan-600/20 flex-shrink-0">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-teal-500 to-cyan-500 flex items-center justify-center">
                <Bot className="w-4.5 h-4.5 text-white" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white leading-tight">SAVIA Assistant</h3>
                <p className="text-[10px] text-teal-300/70">IA • Données en temps réel</p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button onClick={resetChat} className="p-1.5 rounded-lg text-white/40 hover:text-white hover:bg-white/10 transition-colors cursor-pointer" title="Nouvelle conversation">
                <RotateCcw className="w-4 h-4" />
              </button>
              <button onClick={() => setIsOpen(false)} className="p-1.5 rounded-lg text-white/40 hover:text-white hover:bg-white/10 transition-colors cursor-pointer" title="Fermer">
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4 scrollbar-thin">
            {messages.map((msg, i) => (
              <div key={i} className={`flex gap-2.5 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                {/* Avatar */}
                <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5 ${
                  msg.role === 'assistant' 
                    ? 'bg-gradient-to-br from-teal-500 to-cyan-500' 
                    : 'bg-gradient-to-br from-blue-500 to-indigo-500'
                }`}>
                  {msg.role === 'assistant' ? <Bot className="w-3.5 h-3.5 text-white" /> : <User className="w-3.5 h-3.5 text-white" />}
                </div>
                {/* Bubble */}
                <div className={`max-w-[80%] ${msg.role === 'user' ? 'ml-auto' : 'mr-auto'}`}>
                  <div className={`rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-tr-sm'
                      : 'bg-white/[0.07] text-white/90 border border-white/[0.06] rounded-tl-sm'
                  }`}>
                    {msg.content.split('\n').map((line, j) => (
                      <p key={j} className={j > 0 ? 'mt-1.5' : ''}>{line}</p>
                    ))}
                  </div>
                  {/* Suggestions */}
                  {msg.role === 'assistant' && msg.suggestions && msg.suggestions.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {msg.suggestions.map((s, k) => (
                        <button
                          key={k}
                          onClick={() => sendMessage(s)}
                          disabled={isLoading}
                          className="px-2.5 py-1 rounded-full text-[11px] font-medium bg-teal-500/10 text-teal-300 border border-teal-500/20 hover:bg-teal-500/20 hover:border-teal-400/30 transition-all cursor-pointer disabled:opacity-40"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                  <p className="text-[9px] text-white/20 mt-1 px-1">
                    {msg.timestamp.toLocaleTimeString('fr', { hour: '2-digit', minute: '2-digit' })}
                  </p>
                </div>
              </div>
            ))}

            {/* Loading */}
            {isLoading && (
              <div className="flex gap-2.5">
                <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-teal-500 to-cyan-500 flex items-center justify-center flex-shrink-0">
                  <Bot className="w-3.5 h-3.5 text-white" />
                </div>
                <div className="bg-white/[0.07] border border-white/[0.06] rounded-2xl rounded-tl-sm px-4 py-3">
                  <div className="flex items-center gap-2 text-teal-300/70 text-sm">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Analyse en cours...</span>
                  </div>
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <form onSubmit={handleSubmit} className="px-3 py-3 border-t border-white/10 flex-shrink-0">
            <div className="flex items-center gap-2 bg-white/[0.06] border border-white/[0.08] rounded-xl px-3 py-1.5 focus-within:border-teal-500/30 focus-within:bg-white/[0.08] transition-colors">
              <input
                ref={inputRef}
                type="text"
                placeholder="Posez une question..."
                value={input}
                onChange={e => setInput(e.target.value)}
                disabled={isLoading}
                className="flex-1 bg-transparent text-sm text-white placeholder:text-white/30 focus:outline-none py-1.5 disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={!input.trim() || isLoading}
                className="p-2 rounded-lg bg-gradient-to-r from-teal-500 to-cyan-500 text-white disabled:opacity-30 hover:opacity-90 transition-opacity cursor-pointer flex-shrink-0"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}
