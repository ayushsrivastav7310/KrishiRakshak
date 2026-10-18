import React from 'react';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {VoiceHelpline} from './VoiceHelpline.jsx';
import {api} from './api.js';
vi.mock('./api.js',()=>({api:vi.fn()}));
afterEach(cleanup);
beforeEach(()=>{api.mockReset();api.mockImplementation(async path=>{
  if(path==='/voice/config')return {configured:false,enrolled:true};
  if(path==='/voice/calls')return {calls:[]};
  if(path==='/voice/simulate')return {id:'sim-1',status:'active',message:'फसल सलाह',turns:[]};
  return {enrolled:true};
});});
const farm={area:1,unit:'hectares',latitude:26,longitude:80};
it('labels simulation and unconfigured telephony clearly',async()=>{
  render(<VoiceHelpline farm={farm}/>);
  await screen.findByText(/Live telephony is not configured/);
  fireEvent.click(screen.getByRole('button',{name:'Start simulation'}));
  await screen.findByText('फसल सलाह');
  fireEvent.change(screen.getByLabelText('Simulated caller input'),{target:{value:'मंडी भाव'}});
  fireEvent.click(screen.getByRole('button',{name:'Send input'}));
  await waitFor(()=>expect(api).toHaveBeenCalledWith('/voice/simulate',{method:'POST',body:JSON.stringify({callId:'sim-1',text:'मंडी भाव'})}));
});
it('does not invent soil measurements and deletes call history on opt out',async()=>{
  render(<VoiceHelpline farm={farm}/>);
  await screen.findByText(/Live telephony/);
  fireEvent.click(screen.getByLabelText('Save measured irrigation inputs'));
  expect(screen.getByLabelText('Area (m²)').value).toBe('10000');
  expect(screen.getByLabelText('Field capacity (m³/m³)').value).toBe('');
  fireEvent.click(screen.getByRole('button',{name:'Disable and delete call history'}));
  await waitFor(()=>expect(api).toHaveBeenCalledWith('/voice/profile',{method:'DELETE'}));
});
it('shows account call transcripts and backend errors',async()=>{
  api.mockImplementation(async path=>{
    if(path==='/voice/config')return {configured:false,enrolled:true};
    if(path==='/voice/calls')return {calls:[{id:'a',mode:'twilio',status:'completed',createdAt:1,message:'उत्तर',turns:[{input:'पानी',reply:'माप चाहिए'}]}]};
    throw new Error('Source unavailable');
  });
  render(<VoiceHelpline farm={farm}/>);
  await screen.findByText('पानी',{exact:false});
  fireEvent.click(screen.getByRole('button',{name:'Start simulation'}));
  expect((await screen.findByRole('alert')).textContent).toBe('Source unavailable');
});
