import React from 'react';
const steps = ['Describe', 'Diagnostics', 'Urgency', 'Calling Tech', 'Result'];
export default function StepTimeline({ current }) {
  return (
    <div style={{ display:'flex', gap:14, alignItems:'center', justifyContent:'center', padding:'10px 12px', margin:'6px 0 2px' }}>
      {steps.map((s, i) => {
        const active = i <= current;
        return (
          <div key={s} style={{ display:'flex', alignItems:'center', gap:8 }}>
            <span style={{ width:10, height:10, borderRadius:'50%', background: active ? 'var(--primary)' : 'rgba(255,255,255,0.15)', boxShadow: active ? '0 0 10px var(--primary)' : 'none' }} />
            <span style={{ fontFamily:'Orbitron, monospace', fontSize:11, letterSpacing:1, color: active ? 'var(--primary)' : 'rgba(255,255,255,0.5)', textTransform:'uppercase' }}>{s}</span>
            {i < steps.length - 1 && (<div style={{ width:36, height:2, background:'linear-gradient(90deg, rgba(255,255,255,0.06), rgba(255,255,255,0.2))' }} />)}
          </div>
        );
      })}
    </div>
  );
}
