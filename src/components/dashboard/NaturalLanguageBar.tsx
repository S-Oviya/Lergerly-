import React, { useState } from 'react';
import { NLParseResult } from '../../types';
import { SAMPLE_QUICK_COMMANDS } from '../../data/mockData';
import { formatCurrency, formatDate } from '../../utils/formatters';
import { Sparkles, Send, Mic, CheckCircle2, X, ArrowRight, Calendar, Tag, ShieldCheck } from 'lucide-react';

interface NaturalLanguageBarProps {
  onProcessCommand: (input: string) => NLParseResult | null;
  latestResult: NLParseResult | null;
  onClearResult: () => void;
}

export const NaturalLanguageBar: React.FC<NaturalLanguageBarProps> = ({
  onProcessCommand,
  latestResult,
  onClearResult,
}) => {
  const [inputText, setInputText] = useState('');
  const [isListening, setIsListening] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim()) return;
    onProcessCommand(inputText);
    setInputText('');
  };

  const handleQuickClick = (command: string) => {
    setInputText(command);
    onProcessCommand(command);
  };

  const toggleMic = () => {
    // Simulated speech prompt for the hackathon UI
    setIsListening((prev) => !prev);
    if (!isListening) {
      setInputText("Rahul took 2 packets of rice for 500, he'll pay Friday");
    }
  };

  return (
    <div className="bg-gradient-to-r from-emerald-900 via-emerald-800 to-slate-900 rounded-2xl p-5 sm:p-6 text-white shadow-lg relative overflow-hidden">
      {/* Subtle Background Glow */}
      <div className="absolute -right-12 -top-12 w-48 h-48 bg-emerald-500/20 rounded-full blur-3xl pointer-events-none" />

      <div className="relative z-10">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/20 flex items-center justify-center border border-emerald-400/30 text-emerald-300">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-base sm:text-lg font-bold tracking-tight text-white flex items-center gap-2">
                Voice & Text Ledger Assistant
                <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-md bg-emerald-500/30 text-emerald-200 border border-emerald-400/30">
                  Demo AI Flow
                </span>
              </h2>
              <p className="text-xs text-emerald-100/80">
                Speak or type natural kirana notes. Ledgerly extracts the transaction and updates balances.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-emerald-200/90 bg-emerald-950/60 px-3 py-1 rounded-full border border-emerald-700/50 self-start sm:self-auto">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span>Deterministic Math Verification</span>
          </div>
        </div>

        {/* Input Form */}
        <form onSubmit={handleSubmit} className="relative">
          <div className="flex items-center rounded-xl bg-white shadow-inner p-1.5 focus-within:ring-2 focus-within:ring-emerald-400 transition-all">
            <button
              type="button"
              onClick={toggleMic}
              title={isListening ? "Listening... (Click to stop)" : "Simulate voice input"}
              className={`p-2.5 rounded-lg transition-colors flex items-center justify-center ${
                isListening
                  ? 'bg-rose-500 text-white animate-pulse'
                  : 'text-slate-400 hover:text-emerald-700 hover:bg-slate-100'
              }`}
            >
              <Mic className="w-5 h-5" />
            </button>

            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder="e.g. &quot;Rahul took 2 packets of rice for 500, he'll pay Friday&quot; or &quot;Rahul paid 300&quot;"
              className="w-full px-3 py-2 text-sm sm:text-base text-slate-800 placeholder-slate-400 bg-transparent border-none focus:outline-none"
            />

            <button
              type="submit"
              disabled={!inputText.trim()}
              className="px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 disabled:hover:bg-emerald-600 text-white text-sm font-semibold rounded-lg flex items-center gap-1.5 transition-all shrink-0"
            >
              <span>Record</span>
              <Send className="w-3.5 h-3.5" />
            </button>
          </div>
        </form>

        {/* Quick Sample Prompts */}
        <div className="mt-3 flex items-center gap-2 overflow-x-auto pb-1 text-xs no-scrollbar">
          <span className="text-emerald-200/80 font-medium shrink-0">Try saying:</span>
          {SAMPLE_QUICK_COMMANDS.map((cmd, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => handleQuickClick(cmd)}
              className="shrink-0 px-2.5 py-1 rounded-full bg-emerald-800/60 hover:bg-emerald-700/80 text-emerald-100 border border-emerald-600/40 text-xs transition-colors truncate max-w-xs cursor-pointer"
            >
              "{cmd}"
            </button>
          ))}
        </div>

        {/* Confirmation & Extraction Card */}
        {latestResult && (
          <div className="mt-4 bg-white text-slate-900 rounded-xl p-4 shadow-md border-l-4 border-emerald-500 animate-in fade-in duration-200">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-3">
                <div className="w-7 h-7 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center shrink-0 mt-0.5">
                  <CheckCircle2 className="w-4 h-4" />
                </div>
                <div>
                  {/* Primary Output as requested in specification */}
                  <h3 className="text-base font-bold text-slate-900">
                    {latestResult.confirmationText}
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5 italic">
                    Original message: "{latestResult.rawInput}"
                  </p>
                </div>
              </div>
              <button
                onClick={onClearResult}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-md"
                title="Dismiss confirmation"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Extracted Structured Data Breakdown */}
            <div className="mt-3 pt-3 border-t border-slate-100 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
              <div className="bg-slate-50 p-2 rounded-lg">
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Customer</span>
                <span className="font-semibold text-slate-800">{latestResult.customerName}</span>
              </div>
              <div className="bg-slate-50 p-2 rounded-lg">
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Type</span>
                <span className={`font-semibold inline-flex items-center gap-1 ${
                  latestResult.type === 'CREDIT' ? 'text-rose-700' : 'text-emerald-700'
                }`}>
                  <Tag className="w-3 h-3" />
                  {latestResult.type === 'CREDIT' ? 'Credit Given' : 'Payment Received'}
                </span>
              </div>
              <div className="bg-slate-50 p-2 rounded-lg">
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Amount</span>
                <span className="font-bold text-slate-900">{formatCurrency(latestResult.amount)}</span>
              </div>
              <div className="bg-slate-50 p-2 rounded-lg">
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Remaining Khata</span>
                <span className="font-bold text-emerald-800">{formatCurrency(latestResult.customerBalanceAfter)}</span>
              </div>
            </div>

            {latestResult.dueDate && (
              <div className="mt-2 flex items-center gap-1.5 text-xs text-slate-600 bg-amber-50/70 text-amber-900 px-2.5 py-1 rounded-md">
                <Calendar className="w-3.5 h-3.5 text-amber-600" />
                <span>Payment Promised By: <strong>{formatDate(latestResult.dueDate)}</strong></span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
