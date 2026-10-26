const assert=require('node:assert/strict');
const {valid,candidates,appendVin}=require('../static/js/chassi_foto.js');
const a='9C6AAAAAAA0000001',b='9C6AAAAAAA0000002';
assert(valid(a));assert(!valid(a.slice(1)));assert(!valid(a+'1'));
for(const letter of ['I','O','Q'])assert(!valid(letter+a.slice(1)));
assert.deepEqual(candidates('CHASSI: '+a.toLowerCase()),[a]);
assert.deepEqual(candidates(a+'\n'+b+'\n'+a),[a,b]);
assert.deepEqual(candidates('CHASSI: 9C6 AAAAAAA 0000001'),[a]);
assert.deepEqual(candidates(a+'1'),[]);
assert.deepEqual(candidates('9C6AAAAAAO0000001'),[]); // Nunca adivinhar O/0 ou I/1.
assert.deepEqual(candidates('<script>alert(1)</script>'),[]);
assert.equal(appendVin('',a),a);
assert.equal(appendVin(a.toLowerCase(),a),a.toLowerCase());
assert.equal(appendVin(a,b),a+'\n'+b);
assert.throws(()=>appendVin('',a.slice(1)));
console.log('Chassi por foto: validação, candidatos, ambiguidades e duplicidades OK');
