/**
 * Test encoding round-trip
 */

import pako from 'pako';

const project = {
  id: 'test123',
  metadata: { name: 'Test' },
  components: [
    { id: 'c1', type: 'reservoir', name: 'Tank 1' }
  ]
};

console.log('=== Original ===');
console.log(JSON.stringify(project, null, 2));

// Encode
const json = JSON.stringify(project);
const jsonBytes = new TextEncoder().encode(json);
console.log('\nJSON bytes:', jsonBytes.length);

const compressed = pako.gzip(jsonBytes, { level: 6 });
console.log('Compressed bytes:', compressed.length);
console.log('Compressed type:', compressed.constructor.name);
console.log('First 10 bytes:', Array.from(compressed.slice(0, 10)));

// Convert to base64url
const base64 = Buffer.from(compressed).toString('base64');
const base64url = base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
console.log('\nBase64url length:', base64url.length);
console.log('Base64url:', base64url);

// Decode back
console.log('\n=== Decoding ===');
let base64back = base64url.replace(/-/g, '+').replace(/_/g, '/');
const paddingNeeded = (4 - (base64back.length % 4)) % 4;
base64back += '='.repeat(paddingNeeded);

const bytesBack = Buffer.from(base64back, 'base64');
console.log('Decoded bytes:', bytesBack.length);
console.log('First 10 bytes back:', Array.from(bytesBack.slice(0, 10)));

const decompressed = pako.ungzip(bytesBack);
console.log('Decompressed bytes:', decompressed.length);

const jsonBack = new TextDecoder().decode(decompressed);
const projectBack = JSON.parse(jsonBack);

console.log('\n=== Decoded ===');
console.log(JSON.stringify(projectBack, null, 2));
console.log('\n=== Match:', JSON.stringify(project) === JSON.stringify(projectBack));
