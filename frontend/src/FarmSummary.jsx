import React from 'react';
import {MapPin,Tractor,Leaf,Droplets,Sun} from 'lucide-react';
export function FarmSummary({farm}){return <div className="summary-grid">{[[MapPin,'Location',[farm.village,farm.district,farm.state].filter(Boolean).join(', ')||`${farm.latitude}, ${farm.longitude}`],[Tractor,'Land area',`${farm.area} ${farm.unit}`],[Leaf,'Soil type',farm.soilType],[Droplets,'Water availability',farm.water],[Sun,'Sowing month',farm.sowingMonth]].map(([Icon,label,value])=><div key={label}><Icon size={20}/><span><small>{label}</small><strong>{value}</strong></span></div>)}</div>}
