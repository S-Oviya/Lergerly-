import { useState, useRef, useEffect, useCallback } from 'react';

export interface UseSpeechRecognitionOptions {
  onResult?: (transcript: string) => void;
  lang?: string;
}

export interface UseSpeechRecognitionReturn {
  isSupported: boolean;
  isListening: boolean;
  transcript: string;
  error: string | null;
  startListening: () => void;
  stopListening: () => void;
  resetTranscript: () => void;
  clearError: () => void;
}

// Browser Web Speech API type declarations
interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: {
      isFinal: boolean;
      length: number;
      [index: number]: {
        transcript: string;
        confidence: number;
      };
    };
  };
}

interface SpeechRecognitionErrorEventLike {
  error: string;
  message?: string;
}

interface SpeechRecognitionInstance {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

export function useSpeechRecognition({
  onResult,
  lang = 'en-IN',
}: UseSpeechRecognitionOptions = {}): UseSpeechRecognitionReturn {
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const onResultCallbackRef = useRef(onResult);

  // Keep callback reference updated
  useEffect(() => {
    onResultCallbackRef.current = onResult;
  }, [onResult]);

  const isSupported =
    typeof window !== 'undefined' &&
    Boolean((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);

  // Stop listening helper
  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        // Recognition might already be stopped
      }
    }
    setIsListening(false);
  }, []);

  // Start listening helper
  const startListening = useCallback(() => {
    if (!isSupported) {
      setError(
        'Speech recognition is not supported in this browser. Please use Google Chrome, Microsoft Edge, or a supported browser.'
      );
      return;
    }

    setError(null);

    // Stop any existing instance
    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort();
      } catch {
        // Ignore abort errors
      }
    }

    const SpeechRecognitionConstructor =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    try {
      const recognition: SpeechRecognitionInstance = new SpeechRecognitionConstructor();
      recognitionRef.current = recognition;

      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = lang;

      recognition.onstart = () => {
        setIsListening(true);
      };

      recognition.onresult = (event: SpeechRecognitionEventLike) => {
        let interimText = '';
        let finalText = '';

        for (let i = event.resultIndex; i < event.results.length; ++i) {
          const result = event.results[i];
          if (result.isFinal) {
            finalText += result[0].transcript;
          } else {
            interimText += result[0].transcript;
          }
        }

        const recognized = (finalText || interimText).trim();
        if (recognized) {
          setTranscript(recognized);
          if (onResultCallbackRef.current) {
            onResultCallbackRef.current(recognized);
          }
        }
      };

      recognition.onerror = (event: SpeechRecognitionErrorEventLike) => {
        let errorMsg = 'Speech recognition error occurred.';
        switch (event.error) {
          case 'not-allowed':
          case 'service-not-allowed':
            errorMsg =
              'Microphone permission was denied. Please allow microphone access in your browser settings to use voice input.';
            break;
          case 'no-speech':
            errorMsg = 'No speech was detected. Please try speaking again.';
            break;
          case 'audio-capture':
            errorMsg = 'No microphone was found or audio capture failed. Please verify your microphone connection.';
            break;
          case 'network':
            errorMsg = 'Network communication error during speech recognition.';
            break;
          case 'aborted':
            setIsListening(false);
            return;
          default:
            errorMsg = `Speech recognition error: ${event.error}`;
        }
        setError(errorMsg);
        setIsListening(false);
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognition.start();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Could not initialize speech recognition.'
      );
      setIsListening(false);
    }
  }, [isSupported, lang]);

  const resetTranscript = useCallback(() => {
    setTranscript('');
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {
          // Ignore
        }
      }
    };
  }, []);

  return {
    isSupported,
    isListening,
    transcript,
    error,
    startListening,
    stopListening,
    resetTranscript,
    clearError,
  };
}
