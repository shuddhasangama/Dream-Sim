import countries from '../../phone_countries.json' with {type: 'json'};
export {countries};
export function normalizePhone(value, countryCode='IN') {
  const country=countries.find(c=>c.code===countryCode);
  if(!country?.enabled) throw new Error('This country is not available yet.');
  let digits=String(value||'').trim().replace(/[\s()-]/g,'');
  if(digits.startsWith('+'+country.dial)) digits=digits.slice(country.dial.length+1);
  if(!/^[0-9]+$/.test(digits)||!country.lengths.includes(digits.length))
    throw new Error(countryCode==='IN'?'Enter exactly 10 digits for your Indian mobile number.':'Enter a valid mobile number for the selected country.');
  return '+'+country.dial+digits;
}
export function countryOptions() {
  return countries.map(c=>`<option value="${c.code}" ${c.code==='IN'?'selected':''} ${c.enabled?'':'disabled'}>${c.name} (+${c.dial})${c.enabled?'':' — Coming soon'}</option>`).join('');
}
