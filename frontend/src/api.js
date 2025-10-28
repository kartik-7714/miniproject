const API_BASE = 'http://localhost:5000';

export const sendConversation = async (payload) => {
  try {
    let audioBase64 = payload.audioBase64 || '';
    if (audioBase64 && !audioBase64.startsWith('data:')) {
      audioBase64 = `data:audio/webm;base64,${audioBase64}`;
    }
    const res = await fetch(`${API_BASE}/conversation`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...payload, audioBase64 }),
    });
    const body = await res.json().catch(() => null);
    if (!res.ok) {
      const msg = (body && body.agentMessage) || `HTTP ${res.status}`;
      throw new Error(msg);
    }
    return body || {
      transcript: '', agentMessage: 'Server returned empty response.', events: [],
      diagQns: [], diagIdx: 0, diagAnswers: [], userProblem: '', problemType: '', nextStep: 'complete'
    };
  } catch (err) {
    console.error('[API] /conversation failed:', err);
    return {
      transcript: '',
      agentMessage: String(err?.message || 'Could not contact server.'),
      events: [],
      diagQns: [], diagIdx: 0, diagAnswers: [],
      userProblem: '', problemType: '', nextStep: 'complete'
    };
  }
};

export const fetchTTS = async (text) => {
  try {
    const res = await fetch(`${API_BASE}/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error(`TTS failed: ${res.status}`);
    return await res.blob();
  } catch (err) {
    console.error('[TTS Error]', err);
    return null;
  }
};
