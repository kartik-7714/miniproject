import React, { useEffect, useRef } from 'react';
export default function Waveform({ analyser, isRecording, isSpeaking }) {
  const canvasRef = useRef(null);
  useEffect(() => {
    let raf;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const draw = () => {
      const w = canvas.width = canvas.offsetWidth;
      const h = canvas.height = 48;
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = 'rgba(0,0,0,0.25)';
      ctx.fillRect(0, 0, w, h);
      if (analyser) {
        const bufferLength = analyser.fftSize;
        const data = new Uint8Array(bufferLength);
        analyser.getByteTimeDomainData(data);
        ctx.lineWidth = 2;
        const grad = ctx.createLinearGradient(0,0,w,0);
        grad.addColorStop(0, '#00f0ff'); grad.addColorStop(0.5, '#7b2ff7'); grad.addColorStop(1, '#ff006e');
        ctx.strokeStyle = grad;
        ctx.beginPath();
        const slice = w / bufferLength;
        for (let i=0;i<bufferLength;i++){
          const v=(data[i]-128)/128;
          const y = h/2 + v * (isRecording ? 18 : isSpeaking ? 10 : 6);
          const x = i * slice;
          if (i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
        }
        ctx.stroke();
      }
      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(raf);
  }, [analyser, isRecording, isSpeaking]);
  return (<div style={{ padding:'6px 14px 0' }}><canvas ref={canvasRef} style={{ width:'100%', height:48 }} /></div>);
}
