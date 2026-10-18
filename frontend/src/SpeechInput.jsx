import React,{useEffect,useRef,useState} from 'react';

export function SpeechInput({onTranscript,disabled=false}){
 const recognition=useRef(null),[listening,setListening]=useState(false),[error,setError]=useState(''),[language,setLanguage]=useState('hi-IN');
 const Engine=window.SpeechRecognition||window.webkitSpeechRecognition;
 useEffect(()=>()=>{if(recognition.current){recognition.current.onend=null;recognition.current.onerror=null;recognition.current.onresult=null;recognition.current.abort();}},[]);
 function start(){
  setError('');
  if(!window.isSecureContext){setError('Microphone transcription needs HTTPS or localhost.');return;}
  const session=new Engine();recognition.current=session;session.lang=language;session.interimResults=false;session.maxAlternatives=1;
  session.onresult=e=>{const transcript=Array.from(e.results).filter(r=>r.isFinal).map(r=>r[0].transcript).join(' ').trim();if(transcript)onTranscript(transcript);};
  session.onerror=e=>{setListening(false);setError(e.error==='not-allowed'?'Microphone access was denied. Allow microphone access in your browser and try again.':e.error==='no-speech'?'No speech detected. Please try again.':`Speech recognition failed (${e.error}). You can still type your input.`);};
  session.onend=()=>{setListening(false);recognition.current=null;};
  try{session.start();setListening(true);}catch{setError('Unable to start microphone. Please try again.');}
 }
 return <div><label>Speech language<select value={language} disabled={listening||disabled} onChange={e=>setLanguage(e.target.value)}><option value="hi-IN">Hindi</option><option value="en-IN">English (India)</option></select></label>{Engine?<button type="button" className="secondary" disabled={disabled} onClick={()=>listening?recognition.current?.stop():start()}>{listening?'Stop microphone':'Use microphone'}</button>:<p>Microphone transcription is unavailable in this browser. Try Chrome or Edge, or type your input.</p>}{listening&&<p role="status">Listening… Speak now.</p>}{error&&<p role="alert" className="error">{error}</p>}<p className="hint">Your browser’s speech service processes microphone audio. Review the transcript before sending.</p></div>;
}
