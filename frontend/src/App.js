import React from 'react';
import VoiceChat from './components/VoiceChat';

function App() {
  return (
    <main aria-label="AI Call Agent" style={{ minHeight:'100vh', background:'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', display:'flex', alignItems:'center', justifyContent:'center', padding:'20px' }}>
      <section aria-labelledby="app-title" style={{ width:'100%', maxWidth:980 }}>
        <h1 id="app-title" style={{ position:'absolute', left:'-10000px' }}>AI Call Agent</h1>
        <VoiceChat />
      </section>
    </main>
  );
}
export default App;
