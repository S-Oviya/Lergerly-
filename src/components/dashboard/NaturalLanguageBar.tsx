import React, { useState } from 'react';
import { NLParseResult } from '../../types';
import { SAMPLE_QUICK_COMMANDS } from '../../data/mockData';
import { formatCurrency, formatDate } from '../../utils/formatters';
import { useSpeechRecognition } from '../../hooks/useSpeechRecognition';
import { sendMessage, ExtractedTransaction, ApiError } from '../../services/api';
import {
  Sparkles,
  Send,
  Mic,
  MicOff,
  CheckCircle2,
  X,
  Calendar,
  Tag,
  ShieldCheck,
  AlertCircle,
  Loader2,
} from 'lucide-react';

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
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [extractedResult, setExtractedResult] = useState<{
    rawInput: string;
    data: ExtractedTransaction;
  } | null>(null);

  // Built-in browser speech-to-text hook
  const {
    isSupported,
    isListening,
    error: speechError,
    startListening,
    stopListening,
    clearError: clearSpeechError,
    resetTranscript,
  } = useSpeechRecognition({
    onResult: (spokenText) => {
      if (spokenText.trim()) {
        setInputText(spokenText);
        setApiError(null);
      }
    },
    lang: 'en-IN',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = inputText.trim();
    if (!trimmed || isSubmitting) return;

    setIsSubmitting(true);
    setApiError(null);

    try {
      // 1. Send natural language message to API
      const response = await sendMessage(trimmed);

      // 2. If extractedTransaction is returned in response, display confirmation
      if (response && response.extractedTransaction) {
        setExtractedResult({
          rawInput: trimmed,
          data: response.extractedTransaction,
        });

        // Also process through deterministic local ledger to update state
        onProcessCommand(trimmed);
      } else {
        // Fallback for mock / non-extracted response
        onProcessCommand(trimmed);
      }

      // Success: clear input text, speech transcript, and speech error
      setInputText('');
      resetTranscript();
      clearSpeechError();
    } catch (err: unknown) {
      const apiErr = err as ApiError;
      console.warn('Transaction processing error:', apiErr);

      // Handle HTTP 503 (Bedrock unavailable or unconfigured)
      const is503 =
        apiErr?.status === 503 ||
        (typeof apiErr?.message === 'string' &&
          (apiErr.message.includes('503') ||
            apiErr.message.toLowerCase().includes('unavailable') ||
            apiErr.message.toLowerCase().includes('bedrock')));

      if (is503) {
        setApiError(
          'AI transaction processing is currently unavailable. Your message was not processed.'
        );
      } else {
        // Sanitize error: do NOT expose raw AWS stack traces or internal server error dumps
        const rawMsg = apiErr?.message || '';
        if (
          rawMsg.includes('Traceback') ||
          rawMsg.includes('boto3') ||
          rawMsg.includes('ClientError') ||
          rawMsg.includes('Internal server error')
        ) {
          setApiError('Transaction processing failed due to a server error. Your message was not processed.');
        } else {
          setApiError(rawMsg || 'Failed to process transaction. Please try again.');
        }
      }

      // Do NOT display fake extracted data or pretend it succeeded
      setExtractedResult(null);
      onClearResult();

      // Crucial requirement: Keep recognized text in the input box so the user can retry.
      // Notice setInputText is NOT called here!
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleQuickClick = (command: string) => {
    setInputText(command);
    setApiError(null);
  };

  const handleClearResult = () => {
    setExtractedResult(null);
    onClearResult();
  };

  const handleMicToggle = () => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
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
                  Voice Powered
                </span>
              </h2>
              <p className="text-xs text-emerald-100/80">
                Press the mic and speak natural kirana notes, or type. Edit before submitting.
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
            {/* Voice Input Microphone Button */}
            <button
              type="button"
              onClick={handleMicToggle}
              disabled={!isSupported && !isListening}
              title={
                !isSupported
                  ? 'Speech recognition is not supported in this browser'
                  : isListening
                  ? 'Listening... Click to stop recording'
                  : 'Click to speak transaction note'
              }
              className={`p-2.5 rounded-lg transition-all flex items-center justify-center ${
                isListening
                  ? 'bg-rose-500 text-white animate-pulse ring-4 ring-rose-300/50'
                  : !isSupported
                  ? 'text-slate-300 cursor-not-allowed'
                  : 'text-slate-400 hover:text-emerald-700 hover:bg-slate-100 active:scale-95'
              }`}
            >
              {isListening ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
            </button>

            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder={
                isListening
                  ? 'Listening... Speak now...'
                  : 'Speak or type: e.g. "Rahul took rice for 500 on credit"'
              }
              className="w-full px-3 py-2 text-sm sm:text-base text-slate-800 placeholder-slate-400 bg-transparent border-none focus:outline-none"
            />

            <button
              type="submit"
              disabled={!inputText.trim() || isSubmitting}
              className="px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 disabled:hover:bg-emerald-600 text-white text-sm font-semibold rounded-lg flex items-center gap-1.5 transition-all shrink-0 cursor-pointer"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Processing...</span>
                </>
              ) : (
                <>
                  <span>Record</span>
                  <Send className="w-3.5 h-3.5" />
                </>
              )}
            </button>
          </div>

          {/* Active Listening Indicator */}
          {isListening && (
            <div className="mt-2.5 flex items-center justify-between text-xs bg-rose-500/20 border border-rose-400/40 text-rose-100 px-3 py-1.5 rounded-lg animate-in fade-in duration-150">
              <div className="flex items-center gap-2">
                <span className="relative flex h-2.5 w-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-rose-500"></span>
                </span>
                <span>
                  Listening... Speak your transaction note (e.g. &quot;Rahul took rice for 500 on credit&quot;)
                </span>
              </div>
              <button
                type="button"
                onClick={stopListening}
                className="px-2 py-0.5 bg-rose-600/80 hover:bg-rose-700 text-white rounded text-[11px] font-semibold transition-colors"
              >
                Done Speaking
              </button>
            </div>
          )}

          {/* Speech Error / Permission Alert */}
          {speechError && (
            <div className="mt-2.5 flex items-center justify-between text-xs bg-amber-500/20 border border-amber-400/40 text-amber-200 px-3 py-1.5 rounded-lg animate-in fade-in duration-150">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-amber-300 shrink-0" />
                <span>{speechError}</span>
              </div>
              <button
                type="button"
                onClick={clearSpeechError}
                className="text-amber-300 hover:text-white p-0.5 rounded transition-colors"
                title="Dismiss notification"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {/* API / Bedrock 503 Error Alert */}
          {apiError && (
            <div className="mt-2.5 flex items-center justify-between text-xs bg-rose-500/20 border border-rose-400/40 text-rose-100 px-3 py-2 rounded-lg animate-in fade-in duration-150">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-rose-300 shrink-0" />
                <span>{apiError}</span>
              </div>
              <button
                type="button"
                onClick={() => setApiError(null)}
                className="text-rose-300 hover:text-white p-0.5 rounded transition-colors shrink-0 ml-2"
                title="Dismiss error"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
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

        {/* Extracted Transaction Confirmation Card (from POST /message Bedrock extraction) */}
        {extractedResult && (
          <div className="mt-4 bg-white text-slate-900 rounded-xl p-4 shadow-md border-l-4 border-emerald-500 animate-in fade-in duration-200">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-3">
                <div className="w-7 h-7 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center shrink-0 mt-0.5">
                  <CheckCircle2 className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900">
                    Transaction Understood
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5 italic">
                    Original message: &quot;{extractedResult.rawInput}&quot;
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={handleClearResult}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-md transition-colors"
                title="Dismiss confirmation"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Extracted Structured Data Breakdown */}
            <div
              className={`mt-3 pt-3 border-t border-slate-100 grid grid-cols-2 ${
                extractedResult.data.description ? 'sm:grid-cols-4' : 'sm:grid-cols-3'
              } gap-2 text-xs`}
            >
              <div className="bg-slate-50 p-2 rounded-lg">
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Customer</span>
                <span className="font-semibold text-slate-800 truncate block">
                  {extractedResult.data.customerName}
                </span>
              </div>
              <div className="bg-slate-50 p-2 rounded-lg">
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Type</span>
                <span
                  className={`font-semibold inline-flex items-center gap-1 ${
                    extractedResult.data.type === 'CREDIT' ? 'text-rose-700' : 'text-emerald-700'
                  }`}
                >
                  <Tag className="w-3 h-3" />
                  {extractedResult.data.type === 'CREDIT' ? 'Credit' : 'Payment'}
                </span>
              </div>
              <div className="bg-slate-50 p-2 rounded-lg">
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Amount</span>
                <span className="font-bold text-slate-900">
                  {formatCurrency(extractedResult.data.amount)}
                </span>
              </div>
              {extractedResult.data.description && (
                <div className="bg-slate-50 p-2 rounded-lg">
                  <span className="text-slate-500 block text-[10px] uppercase font-semibold">Description</span>
                  <span
                    className="font-semibold text-slate-800 truncate block"
                    title={extractedResult.data.description}
                  >
                    {extractedResult.data.description}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Local Parse Result Fallback (if no backend extractedResult is active) */}
        {!extractedResult && latestResult && (
          <div className="mt-4 bg-white text-slate-900 rounded-xl p-4 shadow-md border-l-4 border-emerald-500 animate-in fade-in duration-200">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-3">
                <div className="w-7 h-7 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center shrink-0 mt-0.5">
                  <CheckCircle2 className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900">
                    {latestResult.confirmationText}
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5 italic">
                    Original message: "{latestResult.rawInput}"
                  </p>
                </div>
              </div>
              <button
                type="button"
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
