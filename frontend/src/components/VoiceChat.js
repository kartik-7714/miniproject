import React, { useState, useRef, useEffect, useCallback } from 'react';
import { sendConversation, fetchTTS } from '../api';
import './VoiceChat.css';
import StepTimeline from './StepTimeline';
import Waveform from './Waveform';

function EscalationBanner({ events }) {
  if (!events || !events.length) return null;
  const stage = events[events.length - 1];
  return (
    <div style={{
      margin:'8px 16px', padding:'10px 14px', borderRadius:12,
      border:'1px solid var(--glass-border)',
      background:'linear-gradient(135deg, rgba(0,240,255,0.08), rgba(123,47,247,0.08))',
      color:'rgba(255,255,255,0.88)', fontSize:12, display:'flex', alignItems:'center', gap:10
    }}>
      <span style={{ width:8, height:8, borderRadius:'50%', background:'var(--primary)', boxShadow:'0 0 8px var(--primary)' }} />
      <span>Escalation: {stage}</span>
    </div>
  );
}

const SILENCE_THRESHOLD = 0.02;  // Increased sensitivity
const SILENCE_MS = 1800;  // 1.8 seconds before stopping
const MAX_UTTERANCE_MS = 15000;  // 15 seconds max recording

const stepIndexMap = { greet:0, describe_problem:0, diagnostic:1, urgency:2, calling:3, complete:4 };

const VoiceChat = () => {
  const [messages, setMessages] = useState([]);
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [escalationEvents, setEscalationEvents] = useState([]);

  const sessionRef = useRef({ step:'greet', diagQns:[], diagIdx:0, diagAnswers:[], userProblem:'', problemType:'' });
  const bootRef = useRef(false);

  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);
  const audioChunksRef = useRef([]);
  const messagesEndRef = useRef(null);

  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const silenceSinceRef = useRef(null);
  const monitorIntervalRef = useRef(null);
  const maxTimerRef = useRef(null);
  const autoArmTimeoutRef = useRef(null);
  const currentAudioRef = useRef(null);

  const scrollToBottom = useCallback(() => { messagesEndRef.current?.scrollIntoView({ behavior:'smooth' }); }, []);
  useEffect(scrollToBottom, [messages, scrollToBottom]);

  const addMessage = useCallback((sender, text) => {
    if (!text) return;
    setMessages(prev => [...prev, { sender, text, ts: Date.now() }]);
  }, []);

  const speak = useCallback(async (text) => {
    if (!text) return;
    try {
      setIsSpeaking(true);
      const audioBlob = await fetchTTS(text);
      if (!audioBlob) {
        setIsSpeaking(false);
        return;
      }
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      currentAudioRef.current = audio;
      
      await new Promise((resolve) => {
        audio.onended = () => { 
          URL.revokeObjectURL(audioUrl);
          setIsSpeaking(false); 
          resolve(); 
        };
        audio.onerror = (err) => { 
          console.error('[Audio Error]', err);
          URL.revokeObjectURL(audioUrl);
          setIsSpeaking(false); 
          resolve(); 
        };
        
        audio.play().catch(err => {
          console.error('[Autoplay Error]', err);
          setTimeout(() => {
            audio.play().catch(() => {
              console.warn('Audio playback failed');
              URL.revokeObjectURL(audioUrl);
              setIsSpeaking(false);
              resolve();
            });
          }, 100);
        });
      });
    } catch (err) {
      console.error('[TTS Error]', err);
      setIsSpeaking(false);
    }
  }, []);

  const initConversation = useCallback(async () => {
    try {
      const resp = await sendConversation({ audioBase64:'', step:'greet', diagQns:[], diagIdx:0, diagAnswers:[], userProblem:'', problemType:'' });
      addMessage('agent', resp.agentMessage);
      await speak(resp.agentMessage);
      sessionRef.current = { step: resp.nextStep, diagQns: resp.diagQns || [], diagIdx: resp.diagIdx ?? 0, diagAnswers: resp.diagAnswers || [], userProblem: resp.userProblem || '', problemType: resp.problemType || '' };
      
      // Auto-start recording after greeting
      if (resp.nextStep !== 'complete') {
        setTimeout(() => {
          console.log('[Auto-starting microphone]');
          startRecording();
        }, 800);
      }
    } catch {
      addMessage('agent', 'Error connecting to support. Please refresh.');
    }
  }, [addMessage, speak]);

  useEffect(() => {
    return () => {
      if (currentAudioRef.current) {
        currentAudioRef.current.pause();
        currentAudioRef.current = null;
      }
      cleanupMedia();
      if (autoArmTimeoutRef.current) clearTimeout(autoArmTimeoutRef.current);
    };
  }, []);

  const cleanupMedia = () => {
    if (monitorIntervalRef.current) { clearInterval(monitorIntervalRef.current); monitorIntervalRef.current = null; }
    if (maxTimerRef.current) { clearTimeout(maxTimerRef.current); maxTimerRef.current = null; }
    if (audioContextRef.current) {
      try { audioContextRef.current.close(); } catch {}
      audioContextRef.current = null; analyserRef.current = null;
    }
    silenceSinceRef.current = null;
    if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
  };

  const startRecording = async () => {
    // First click initializes conversation
    if (!bootRef.current) {
      bootRef.current = true;
      await initConversation();
      return;
    }

    const { step } = sessionRef.current;
    if (isRecording || isProcessing || isSpeaking) return;
    if (step === 'complete') { addMessage('agent', 'This session is complete. Please refresh to start over.'); return; }
    
    try {
      if (currentAudioRef.current) currentAudioRef.current.pause();
      const stream = await navigator.mediaDevices.getUserMedia({ audio:true });
      streamRef.current = stream;

      const options = MediaRecorder.isTypeSupported('audio/webm') ? { mimeType:'audio/webm' } : {};
      const mr = new MediaRecorder(stream, options);
      mediaRecorderRef.current = mr;
      audioChunksRef.current = [];

      const ACtx = window.AudioContext || window.webkitAudioContext;
      const ctx = new ACtx(); audioContextRef.current = ctx;
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser(); analyser.fftSize = 2048;
      source.connect(analyser); analyserRef.current = analyser;

      const monitor = () => {
        if (!analyserRef.current || !isRecording) return;
        const size = analyserRef.current.fftSize;
        const data = new Uint8Array(size);
        analyserRef.current.getByteTimeDomainData(data);
        let sum = 0; for (let i=0;i<data.length;i++){ const v=(data[i]-128)/128; sum += v*v; }
        const rms = Math.sqrt(sum / data.length);
        const now = performance.now();
        if (rms < SILENCE_THRESHOLD) {
          if (!silenceSinceRef.current) silenceSinceRef.current = now;
          if (now - silenceSinceRef.current > SILENCE_MS) { if (mediaRecorderRef.current?.state==='recording') mediaRecorderRef.current.stop(); }
        } else { silenceSinceRef.current = null; }
      };

      monitorIntervalRef.current = setInterval(monitor, 120);
      maxTimerRef.current = setTimeout(() => { if (mediaRecorderRef.current?.state==='recording') mediaRecorderRef.current.stop(); }, MAX_UTTERANCE_MS);

      mr.ondataavailable = (e) => { if (e.data && e.data.size > 0) audioChunksRef.current.push(e.data); };
      mr.onstop = async () => {
        try {
          const blob = new Blob(audioChunksRef.current, { type:'audio/webm' });
          if (blob.size < 500) { addMessage('agent','Audio too short; please try again.'); return; }
          await processAudio(blob);
        } finally {
          setIsRecording(false);
          cleanupMedia();
        }
      };

      mr.start(); setIsRecording(true);
    } catch {
      addMessage('agent', 'Microphone access denied. Please enable it and try again.');
    }
  };

  const stopRecording = () => { if (mediaRecorderRef.current && isRecording) mediaRecorderRef.current.stop(); };

  const processAudio = async (blob) => {
    setIsProcessing(true);
    try {
      const reader = new FileReader();
      reader.onloadend = async () => {
        const fullDataUrl = reader.result;
        const payload = { ...sessionRef.current, audioBase64: fullDataUrl };
        try {
          const resp = await sendConversation(payload);

          if (resp.nextStep === 'calling') {
            if (resp.agentMessage) { addMessage('agent', resp.agentMessage); await speak(resp.agentMessage); }
            if (Array.isArray(resp.events) && resp.events.length) {
              for (const evt of resp.events) { addMessage('agent', evt); await speak(evt); await new Promise(r => setTimeout(r, 200)); }
            }
            const callPayload = { ...sessionRef.current, step:'calling', audioBase64:'' };
            try {
              const callResp = await sendConversation(callPayload);
              if (Array.isArray(callResp.events) && callResp.events.length) {
                setEscalationEvents(callResp.events);
                for (const evt of callResp.events) { addMessage('agent', evt); await speak(evt); await new Promise(r => setTimeout(r, 200)); }
              } else { setEscalationEvents([]); }
              if (callResp.agentMessage) { addMessage('agent', callResp.agentMessage); await speak(callResp.agentMessage); }
              sessionRef.current = { ...sessionRef.current, step: callResp.nextStep, diagQns: callResp.diagQns || [], diagIdx: callResp.diagIdx ?? 0, diagAnswers: callResp.diagAnswers || [], userProblem: callResp.userProblem || sessionRef.current.userProblem, problemType: callResp.problemType || sessionRef.current.problemType };
              if (callResp.nextStep !== 'complete') { if (autoArmTimeoutRef.current) clearTimeout(autoArmTimeoutRef.current); autoArmTimeoutRef.current = setTimeout(() => startRecording(), 500); }
            } catch {
              addMessage('agent','Call escalation failed. Please try again soon.');
            } finally { setIsProcessing(false); }
            return;
          }

          if (resp.transcript) addMessage('user', resp.transcript);
          if (Array.isArray(resp.events) && resp.events.length) {
            setEscalationEvents(resp.events);
            for (const evt of resp.events) { addMessage('agent', evt); await speak(evt); await new Promise(r => setTimeout(r, 200)); }
          } else { setEscalationEvents([]); }
          if (resp.agentMessage) { addMessage('agent', resp.agentMessage); await speak(resp.agentMessage); }

          sessionRef.current = {
            step: resp.nextStep,
            diagQns: resp.diagQns || [],
            diagIdx: resp.diagIdx ?? 0,
            diagAnswers: resp.diagAnswers || [],
            userProblem: resp.userProblem || sessionRef.current.userProblem,
            problemType: resp.problemType || sessionRef.current.problemType
          };

          if (autoArmTimeoutRef.current) clearTimeout(autoArmTimeoutRef.current);
          if (resp.nextStep !== 'complete') { autoArmTimeoutRef.current = setTimeout(() => startRecording(), 500); }
        } catch {
          addMessage('agent','Could not contact server. Please try again.');
        } finally { setIsProcessing(false); }
      };
      reader.readAsDataURL(blob);
    } catch {
      addMessage('agent','Error processing your request. Please try again.');
      setIsProcessing(false);
    }
  };

  const currentIdx = stepIndexMap[sessionRef.current?.step] ?? 0;

  return (
    <div className={`page ${messages.length ? 'has-messages' : ''}`}>
      <div className="voice-chat-container">
        <div className="chat-header">
          <h1>⚡ AI CALL AGENT</h1>
          <p className="status-text">
            {isSpeaking ? '🔊 SPEAKING' : isRecording ? '🔴 RECORDING' : isProcessing ? '⏳ PROCESSING' : '✓ READY'}
          </p>
          <StepTimeline current={currentIdx} />
        </div>

        <Waveform analyser={analyserRef.current || null} isRecording={isRecording} isSpeaking={isSpeaking} />
        <EscalationBanner events={escalationEvents} />

        <div className="messages-container">
          {messages.map((m, i) => (
            <div key={m.ts ?? i} className={`message ${m.sender}`}>
              <div className="message-bubble">
                <strong>{m.sender === 'agent' ? '🤖 AI AGENT' : '👤 YOU'}</strong>
                <p>{m.text}</p>
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        <div className="controls">
          <button className={`record-btn ${isRecording ? 'recording' : ''}`} onClick={isRecording ? stopRecording : startRecording} disabled={isProcessing || isSpeaking} title="Click to start voice input">
            <span>{isRecording ? '⏹' : '🎤'}<div style={{ fontSize:'12px', marginTop:'4px' }}>{isRecording ? 'STOP' : 'START'}</div></span>
          </button>
        </div>

        <div className="footer-note">
          <small>◆ NEURAL VOICE ELEVENLABS TTS ◆ VOSK STT ◆ AUTO RECORDING ◆</small>
        </div>
      </div>
    </div>
  );
};

export default VoiceChat;
