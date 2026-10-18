import React from 'react';
import {render,screen,fireEvent,cleanup} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {SpeechInput} from './SpeechInput.jsx';
afterEach(()=>{cleanup();delete window.SpeechRecognition;});
it('puts recognized speech into the editable transcript and releases the microphone',()=>{
 let session;const abort=vi.fn();window.SpeechRecognition=class{constructor(){session=this;}start(){}abort=abort;};Object.defineProperty(window,'isSecureContext',{value:true,configurable:true});
 const onTranscript=vi.fn();const view=render(<SpeechInput onTranscript={onTranscript}/>);fireEvent.click(screen.getByRole('button',{name:'Use microphone'}));
 expect(session.lang).toBe('hi-IN');session.onresult({results:[Object.assign([{transcript:'पानी कब दें'}],{isFinal:true})]});expect(onTranscript).toHaveBeenCalledWith('पानी कब दें');view.unmount();expect(abort).toHaveBeenCalled();
});
it('explains unsupported speech recognition',()=>{render(<SpeechInput onTranscript={()=>{}}/>);expect(screen.getByText(/Microphone transcription is unavailable/)).toBeTruthy();});
