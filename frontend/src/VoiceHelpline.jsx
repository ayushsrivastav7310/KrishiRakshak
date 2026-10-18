import React, {useEffect, useState} from 'react';
import {api} from './api.js';
import './voice.css';
import {SpeechInput} from './SpeechInput.jsx';

const irrigationFields = [
  ['plantingDate','Planting date','date'], ['areaM2','Area (m²)','number'],
  ['latitude','Latitude','number'], ['longitude','Longitude','number'],
  ['fieldCapacity','Field capacity (m³/m³)','number'], ['wiltingPoint','Wilting point (m³/m³)','number'],
  ['rootDepthM','Root depth (m)','number'], ['depletionMm','Current depletion before recent irrigation (mm)','number'],
];

export function VoiceHelpline({farm}) {
  const [config,setConfig]=useState(null), [calls,setCalls]=useState([]), [error,setError]=useState('');
  const [notice,setNotice]=useState(''), [pin,setPin]=useState(''), [consent,setConsent]=useState(false);
  const [busy,setBusy]=useState(false), [sim,setSim]=useState(null), [text,setText]=useState('');
  const [useIrrigation,setUseIrrigation]=useState(false);
  const [irrigation,setIrrigation]=useState({crop:'wheat',latitude:farm.latitude??'',longitude:farm.longitude??'',areaM2:farm.area*(farm.unit==='acres'?4046.8564224:10000)});
  useEffect(()=>{
    let alive=true;
    async function refresh(){
      try {
        const [c,h]=await Promise.all([api('/voice/config'),api('/voice/calls')]);
        if(alive){setConfig(c);setCalls(h.calls);}
      } catch(e){if(alive)setError(e.message);}
    }
    refresh();
    const timer=setInterval(refresh,5000);
    return ()=>{alive=false;clearInterval(timer);};
  },[]);
  async function act(fn){setBusy(true);setError('');setNotice('');try{await fn();}catch(e){setError(e.message);}finally{setBusy(false);}}
  async function reload(){const [c,h]=await Promise.all([api('/voice/config'),api('/voice/calls')]);setConfig(c);setCalls(h.calls);}
  async function enroll(e){e.preventDefault();await act(async()=>{
    const inputs=useIrrigation?Object.fromEntries(Object.entries(irrigation).filter(([,v])=>v!=='')):null;
    await api('/voice/profile',{method:'PUT',body:JSON.stringify({pin,consent,irrigation:inputs})});
    setPin('');setConsent(false);setSim(null);await reload();setNotice('Helpline enabled for your account phone. Existing calls were revoked.');
  });}
  async function simulate(e){e.preventDefault();await act(async()=>{
    const result=await api('/voice/simulate',{method:'POST',body:JSON.stringify(sim?.status==='active'?{callId:sim.id,text}:{})});
    setSim(result);setText('');await reload();
  });}
  return <section className="farm-summary voice-helpline" aria-label="AI Voice Helpline">
    <h2>AI Voice Helpline / आवाज़ सहायता</h2>
    <p>Call from a keypad phone, enter your helpline PIN, then speak Hindi or press 1 for crop advice, 2 for irrigation, or 3 for mandi prices.</p>
    {config?.configured&&config?.phone&&<a className="primary" href={`tel:${config.phone}`}>Call helpline: {config.phone}</a>}
    <p role="status">{config?.configured?`Provider configured: ${config.phone}. Real calls have not been verified.`:'Live telephony is not configured. The simulator uses typed transcripts; it does not test speech recognition or place calls.'}</p>
    {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="success" role="status">{notice}</p>}
    <form onSubmit={enroll}>
      <h3>{config?.enrolled?'Update helpline PIN and inputs':'Enable helpline'}</h3>
      <p>Use the phone registered to this account. PINs are hashed. Written call transcripts are saved privately; audio is not recorded by this app.</p>
      <label>New six-digit helpline PIN <input aria-label="Helpline PIN" type="password" inputMode="numeric" pattern="[0-9]{6}" minLength={6} maxLength={6} autoComplete="new-password" required value={pin} onChange={e=>setPin(e.target.value)}/></label>
      <label><input type="checkbox" checked={useIrrigation} onChange={e=>{setUseIrrigation(e.target.checked);if(e.target.checked&&config?.irrigation)setIrrigation(config.irrigation);}}/> Save measured irrigation inputs</label>
      {useIrrigation&&<fieldset><legend>Irrigation measurements</legend>
        <p>Enter measured values; no values are inferred from photos. These inputs are reused on calls until you update them. Current depletion must be updated before each advice call.</p>
        <label>Crop <select aria-label="Irrigation crop" value={irrigation.crop} onChange={e=>setIrrigation({...irrigation,crop:e.target.value})}><option value="wheat">Wheat</option><option value="maize">Maize</option><option value="tomato">Tomato</option></select></label>
        {irrigationFields.map(([key,label,type])=><label key={key}>{label}<input aria-label={label} required type={type} step={type==='number'?'any':undefined} value={irrigation[key]??''} onChange={e=>setIrrigation({...irrigation,[key]:e.target.value})}/></label>)}
      </fieldset>}
      <label><input type="checkbox" required checked={consent} onChange={e=>setConsent(e.target.checked)}/> I consent to storing written call transcripts in my account.</label>
      <button className="primary" disabled={busy||!config}>{config?.enrolled?'Save new PIN and inputs':'Enable helpline'}</button>
      {config?.enrolled&&<button type="button" className="secondary" disabled={busy} onClick={()=>act(async()=>{await api('/voice/profile',{method:'DELETE'});setSim(null);await reload();setNotice('Helpline disabled and call transcripts deleted.');})}>Disable and delete call history</button>}
    </form>
    {config?.enrolled&&<form onSubmit={simulate}>
      <h3>Call simulator — no telephone call</h3>
      <p>Type or use the microphone for Hindi or English, or enter keypad digits. Crop advice asks for seven numeric measurements. For decimal keypad values, use *; on a real phone finish with #. In the main menu, 9 repeats and 0 ends.</p>
      {sim&&<p role="status" lang="hi">{sim.message}</p>}
      {sim?.status==='active'&&<SpeechInput disabled={busy} onTranscript={setText}/>}
      {sim?.status==='active'&&<label>Simulated caller input <input aria-label="Simulated caller input" value={text} maxLength={500} onChange={e=>setText(e.target.value)}/></label>}
      <button className="secondary" disabled={busy}>{sim?.status==='active'?'Send input':'Start simulation'}</button>
      {sim&&<button type="button" className="text-button" onClick={()=>{setSim(null);setText('');}}>New simulation</button>}
    </form>}
    <h3>My recent calls</h3><p>Refreshes every five seconds. Only this account’s calls are visible. Calls expire after 15 minutes; an active label can remain until a callback arrives.</p>
    {!calls.length&&<p>No calls yet.</p>}
    {calls.map(call=><details key={call.id}><summary>{new Date(call.createdAt*1000).toLocaleString()} · {call.mode==='simulation'?'Simulation':'Twilio'} · {call.status} · {call.turns.length} turns</summary>
      <p lang="hi">{call.message}</p>
      <ol>{call.turns.map((turn,i)=><li key={i}><p><strong>Caller:</strong> {turn.input||'(silence)'}</p><p lang="hi"><strong>Helpline:</strong> {turn.reply}</p></li>)}</ol>
    </details>)}
  </section>;
}
