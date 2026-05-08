'use client';
// ==========================================
// 🤖 SAVIA AI Chatbot — Assistant conversationnel flottant (Light Theme)
// ==========================================
import { useState, useRef, useEffect, useCallback } from 'react';
import { X, Send, Loader2, Sparkles, RotateCcw, Bot, User } from 'lucide-react';
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

  useEffect(() => {
    if (isOpen) setPulse(false);
  }, [isOpen]);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || isLoading) return;
    const userMsg: ChatMessage = { role: 'user', content: text.trim(), timestamp: new Date() };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

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
      const msg = err.message || '';
      const isQuota = msg.includes('Quota') || msg.includes('503') || msg.includes('429') || msg.includes('UNAVAILABLE') || msg.includes('exhausted') || msg.includes('Timeout');
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: isQuota
          ? "⏳ L'IA est temporairement surchargée (quota atteint). Veuillez réessayer dans environ 1 minute.\n\n💡 Astuce : les quotas se réinitialisent chaque minute. Votre question sera traitée dès que le quota sera disponible."
          : `❌ Erreur: ${msg || "L'IA n'est pas disponible pour le moment."}`,
        suggestions: isQuota ? ['🔄 Réessayer ma question'] : undefined,
        timestamp: new Date(),
      }]);
      // Store last question for retry
      if (isQuota) {
        setInput(text.trim());
      }
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
          className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full text-white flex items-center justify-center hover:scale-110 active:scale-95 transition-all duration-300 cursor-pointer group"
          style={{ background: 'linear-gradient(135deg, #567C8D, #2F4156)', boxShadow: '4px 4px 10px #e3dac7, -2px -2px 6px #ffffff, 0 4px 20px rgba(86,124,141,0.3)' }}
          aria-label="Ouvrir l'assistant IA"
        >
          <Sparkles className="w-6 h-6 group-hover:rotate-12 transition-transform" />
          {pulse && (
            <span className="absolute inset-0 rounded-full animate-ping opacity-30" style={{ background: '#567C8D' }} />
          )}
        </button>
      )}

      {/* ── Chat Panel ── */}
      {isOpen && (
        <div
          className="fixed bottom-6 right-6 z-50 w-[400px] max-w-[calc(100vw-2rem)] h-[600px] max-h-[calc(100vh-4rem)] flex flex-col rounded-2xl overflow-hidden"
          style={{
            background: '#FAF6ED',
            boxShadow: '8px 8px 20px #e3dac7, -8px -8px 20px #ffffff, 0 8px 32px rgba(47,65,86,0.12)',
          }}
        >

          {/* Header */}
          <div
            className="flex items-center justify-between px-4 py-3 flex-shrink-0"
            style={{ background: 'linear-gradient(135deg, #567C8D, #2F4156)' }}
          >
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(255,255,255,0.2)' }}>
                <Bot className="w-4.5 h-4.5 text-white" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white leading-tight">SAVIA Assistant</h3>
                <p className="text-[10px] text-white/60">IA • Données en temps réel</p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button onClick={resetChat} className="p-1.5 rounded-lg text-white/50 hover:text-white hover:bg-white/15 transition-colors cursor-pointer" title="Nouvelle conversation">
                <RotateCcw className="w-4 h-4" />
              </button>
              <button onClick={() => setIsOpen(false)} className="p-1.5 rounded-lg text-white/50 hover:text-white hover:bg-white/15 transition-colors cursor-pointer" title="Fermer">
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
            {messages.map((msg, i) => (
              <div key={i} className={`flex gap-2.5 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                {/* Avatar */}
                <div
                  className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5"
                  style={{
                    background: msg.role === 'assistant'
                      ? 'linear-gradient(135deg, #567C8D, #2F4156)'
                      : 'linear-gradient(135deg, #8AAAB8, #567C8D)',
                  }}
                >
                  {msg.role === 'assistant' ? <Bot className="w-3.5 h-3.5 text-white" /> : <User className="w-3.5 h-3.5 text-white" />}
                </div>
                {/* Bubble */}
                <div className={`max-w-[80%] ${msg.role === 'user' ? 'ml-auto' : 'mr-auto'}`}>
                  <div
                    className="rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed"
                    style={msg.role === 'user'
                      ? { background: 'linear-gradient(135deg, #567C8D, #2F4156)', color: '#fff', borderTopRightRadius: '4px' }
                      : { background: '#EEF3F6', color: '#2F4156', borderTopLeftRadius: '4px', boxShadow: '2px 2px 6px #e3dac7, -2px -2px 6px #ffffff' }
                    }
                  >
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
                          className="px-2.5 py-1 rounded-full text-[11px] font-medium transition-all cursor-pointer disabled:opacity-40"
                          style={{
                            background: 'rgba(86,124,141,0.08)',
                            color: '#567C8D',
                            border: '1px solid rgba(86,124,141,0.2)',
                          }}
                          onMouseEnter={e => { e.currentTarget.style.background = 'rgba(86,124,141,0.15)'; e.currentTarget.style.borderColor = 'rgba(86,124,141,0.35)'; }}
                          onMouseLeave={e => { e.currentTarget.style.background = 'rgba(86,124,141,0.08)'; e.currentTarget.style.borderColor = 'rgba(86,124,141,0.2)'; }}
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                  <p className="text-[9px] mt-1 px-1" style={{ color: '#8AAAB8' }}>
                    {msg.timestamp.toLocaleTimeString('fr', { hour: '2-digit', minute: '2-digit' })}
                  </p>
                </div>
              </div>
            ))}

            {/* Loading */}
            {isLoading && (
              <div className="flex gap-2.5">
                <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: 'linear-gradient(135deg, #567C8D, #2F4156)' }}>
                  <Bot className="w-3.5 h-3.5 text-white" />
                </div>
                <div className="rounded-2xl rounded-tl-sm px-4 py-3" style={{ background: '#EEF3F6', boxShadow: '2px 2px 6px #e3dac7, -2px -2px 6px #ffffff' }}>
                  <div className="flex items-center gap-2 text-sm" style={{ color: '#567C8D' }}>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Analyse en cours...</span>
                  </div>
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <form onSubmit={handleSubmit} className="px-3 py-3 flex-shrink-0" style={{ borderTop: '1px solid rgba(86,124,141,0.12)' }}>
            <div
              className="flex items-center gap-2 rounded-xl px-3 py-1.5 transition-colors"
              style={{ background: '#EEF3F6', boxShadow: 'inset 2px 2px 4px #e3dac7, inset -2px -2px 4px #ffffff' }}
            >
              <input
                ref={inputRef}
                type="text"
                placeholder="Posez une question..."
                value={input}
                onChange={e => setInput(e.target.value)}
                disabled={isLoading}
                className="flex-1 bg-transparent text-sm focus:outline-none py-1.5 disabled:opacity-50"
                style={{ color: '#2F4156' }}
              />
              <button
                type="submit"
                disabled={!input.trim() || isLoading}
                className="p-2 rounded-lg text-white disabled:opacity-30 hover:opacity-90 transition-opacity cursor-pointer flex-shrink-0"
                style={{ background: 'linear-gradient(135deg, #567C8D, #2F4156)' }}
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
