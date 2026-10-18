import React from 'react';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {FarmSupport} from './FarmSupport.jsx';
import {api} from './api.js';
vi.mock('./api.js',()=>({api:vi.fn()}));
afterEach(cleanup);
beforeEach(()=>{api.mockReset();api.mockImplementation(async path=>{
 if(path==='/diseases/supported')return {available:false,crops:[]};
 if(path.includes('history')||path.includes('recommendations'))return {history:[]};
 if(path.startsWith('/mandi/prices'))return {records:[],total:0};
 if(path==='/mandi/sync-status')return {count:0};
 throw new Error('Source unavailable');
});});
const farm={area:1,unit:'hectares',latitude:26,longitude:80,soilType:'loamy',previousCrop:'maize',state:'Uttar Pradesh',district:'Lucknow'};
it('clearly disables disease analysis without a verified model',async()=>{
 render(<FarmSupport farm={farm}/>);
 await screen.findByText(/verified disease model is not installed/);
 expect(screen.getByRole('button',{name:'Analyze disease'}).disabled).toBe(true);
});
it('reuses profile values and preserves missing soil-water inputs',async()=>{
 render(<FarmSupport farm={farm}/>);
 fireEvent.click(screen.getByRole('tab',{name:'Irrigation'}));
 expect(screen.getByLabelText('Field area (m²)').value).toBe('10000');
 expect(screen.getByLabelText('Farm latitude').value).toBe('26');
 expect(screen.getByLabelText(/Field capacity/).value).toBe('');
 await waitFor(()=>expect(api).toHaveBeenCalledWith('/irrigation/history'));
});
it('shows an explicit empty government-data state',async()=>{
 render(<FarmSupport farm={farm}/>);
 fireEvent.click(screen.getByRole('tab',{name:'Mandi prices'}));
 await screen.findByText(/No government observations match/);
 expect(screen.getByLabelText('State').value).toBe('Uttar Pradesh');
 expect(screen.queryByRole('table')).toBeNull();
});
