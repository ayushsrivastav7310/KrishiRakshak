// Run against the isolated test server described in docs/PHASE_2_SETUP.md.
import {createRequire} from 'node:module';
import {writeFileSync} from 'node:fs';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base='http://127.0.0.1:8011';
const browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
const context=await browser.newContext();
const checks=[];
try {
 const origin={Origin:base};
 for(const [path,body] of [['/api/auth/request-otp',{phone:'+919876500101'}],['/api/auth/verify-otp',{phone:'+919876500101',otp:'654321'}]]){
  const response=await context.request.post(base+path,{data:body,headers:origin});
  if(!response.ok())throw Error(await response.text());
 }
 const saved=await context.request.put(base+'/api/farm',{headers:origin,data:{farmerName:'Phase Two Test',farmName:'Test Farm',latitude:26.85,longitude:80.95,area:2,unit:'acres',soilType:'loamy',water:'rainfed',sowingMonth:'June'}});
 if(!saved.ok())throw Error(await saved.text());
 await context.clearCookies();
 const page=await context.newPage();
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.goto(base);
 await page.getByRole('button',{name:'Let’s grow together'}).click();
 await page.getByRole('textbox',{name:'Phone number',exact:true}).fill('9876500101');
 await page.getByRole('button',{name:'Continue',exact:true}).click();
 await page.getByLabel('Six-digit verification code').fill('654321');
 await page.getByRole('button',{name:'Verify and continue'}).click();
 await page.getByRole('heading',{name:'Crop Intelligence',exact:true}).waitFor();checks.push('Phase 1 login and returning farmer dashboard');
 await page.getByText('Soil model: ready · Crop model: ready').waitFor();
 const inputs=[['Nitrogen (dataset scale)','90'],['Phosphorus (dataset scale)','42'],['Potassium (dataset scale)','43'],['Soil pH','6.5'],['Temperature (°C)','20.88'],['Relative humidity (%)','82'],['Rainfall (mm)','202']];
 for(const [name,value] of inputs)await page.getByRole('spinbutton',{name,exact:true}).fill(value);
 await page.getByRole('button',{name:'Recommend Crops',exact:true}).click();
 await page.getByRole('heading',{name:'Crop to consider: rice',exact:true}).waitFor();checks.push('Real crop recommendation through built frontend');
 await page.getByLabel('Soil photograph').setInputFiles('backend/data/ml/browser-soil.png');
 await page.getByRole('button',{name:'Analyze Soil',exact:true}).click();
 await page.getByText(/Model confidence:/).waitFor();checks.push('Real soil inference through built frontend (synthetic brown image; no accuracy claim)');
 await page.getByLabel('Confirm or correct soil type').fill('Loamy');
 await page.getByRole('button',{name:'Save manual confirmation',exact:true}).click();
 await page.getByText('Your soil correction was saved.').waitFor();checks.push('Manual correction persisted');
 await page.getByRole('button',{name:'Auto-fill weather',exact:true}).click();
 await page.getByText('Temperature and humidity filled from weather estimates. You can edit both.').waitFor({timeout:20000});
 if(await page.getByRole('spinbutton',{name:'Rainfall (mm)',exact:true}).inputValue()!=='202')throw Error('Weather overwrote rainfall');checks.push('Live Open-Meteo autofill preserves rainfall');
 await page.reload();
 await page.getByText('Manual soil: Loamy',{exact:false}).waitFor();checks.push('Session and history survive reload');
 await page.setViewportSize({width:390,height:844});
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Mobile horizontal overflow');
 await page.screenshot({path:'backend/data/phase2-browser.png',fullPage:true});checks.push('390px viewport: no horizontal overflow');
 await page.getByRole('button',{name:'Log out',exact:true}).click();
 await page.getByRole('button',{name:'Let’s grow together'}).waitFor();checks.push('Phase 1 logout');
 if(errors.length)throw Error(errors.join('\n'));
 writeFileSync('docs/browser-smoke.json',JSON.stringify({checks,pageErrors:errors,date:new Date().toISOString()},null,2));
 console.log(JSON.stringify({passed:checks.length,checks}));
}finally{await browser.close();}
