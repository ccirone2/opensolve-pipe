/**
 * Test decoding of generated project URL
 */

import pako from 'pako';

const encoded = process.argv[2] || 'H4sIAAAAAAAAA9VWTW_bOBD9K4LOTkrJVuL42qI9FQi2wR42CAhaGtscUKSWpOx4A__3nSH1lbrfaA4L-GA-PZIz7w3JeU5lla7Sxpq_eXZ9dTNn88XNMrtivILapLO0Bi8q4UW6ek61qAHJt23dQJXcWaHdBmzy6eg81MitwJVWNl4ajbQ_wIHdG2kTbxIv9GPi-xkH6XdJg8skQleJdEYJmpTshdqDw5VKC8IDRZaz_OqCZRd5cceyVZat5stLDO8vCs1UciO_wcqItQfrYkBZepqlDryXeeson1ZLH_64mMEqlZiZlULhPAV663eIbTylJjF3D5Y4GseNBedaS3I0TiKwA1EFMg__ZulGmQMCH24_hiCUKaU_BsYbyhD3w62Ej2u8J450pXFI4o9SQ42KlIGeB_74tTqiD-FbeRtE1y6urNZvNn5OSYIWawUVL3dQPmKG9w-YuEFtLTfBnpB1LZ649BRERDLGMC6jENElRsUuGctmmG-p2gp4FImXrd3jR29biElypG-B16jLir2ExFO6KlgPNkZq0rvITieCWiq959QfG5LgIEjez4S5WiKzNHVjNIS598-xYAnjtq8wntHEuM4AItQV7Ke2DOV1h0WIKCjYi1ikGFrYlyMEiiRAa42d7mRar8CHHbTBJIXiTv6Lyy6oKiyUXbmv5TDC-jmh4pU5aOexklE0o3X8Flf2wm5x0SEzPiYVzkDYrpENVipJhP8gOuZjeSJX2LXRHC0BqlaHVletomwXbBLqWLeLsaRzRvrL_iDcDx6AWqNPN4wrUu-fVmgfSis7PZzwN5uKP8bZTQ7Aueh_dvBL1ePsbuYW00rPhJcadf-e6pE0RBbN-t6kjvXrHtHV9boWFS8dOpd_CKHTkMaj-MPdfBvhl-KHI9ylE_7SOq4BukrxwDuPp8-RTvrcFRdt_UlfKry9dqTnq1sTCyt_TW-yrx2fcN12EbgDbf5jhyj_6iF61-v2pWNU_N-PETUFr3uM8En7yatuQSJMBOW9I982ckilm-rjU9Pfhd5YgSaeP0AFm_YWOY4wm_41ohG-0d1ozugtlh5V6aHizG0a_ta36oG-fgbNwm3DlVxbYY-TR3m4TL50DSVvQ-dAOel2I0p64amf-gAarS5jQ0dZYc90sXhaXGQF-WupEeT97XRNglGXprBNmXi-vAxayL5JiN0X6_uyjJ68Hi1GOFuOcGh_ejyf4BM-m-D5yF9OlslH-vVk0_nIXkzY85GNIaLYp_8AvCMdr5ILAAA';

// Convert base64url to regular base64
let base64 = encoded.replace(/-/g, '+').replace(/_/g, '/');

// Add padding if needed
const paddingNeeded = (4 - (base64.length % 4)) % 4;
base64 += '='.repeat(paddingNeeded);

console.log('Input length:', encoded.length);
console.log('Base64 length after padding:', base64.length);

try {
  // Decode base64 to bytes
  const bytes = Buffer.from(base64, 'base64');
  console.log('Decoded bytes length:', bytes.length);

  // Decompress
  const decompressed = pako.ungzip(bytes);
  console.log('Decompressed length:', decompressed.length);

  // Decode to string
  const json = new TextDecoder().decode(decompressed);

  // Parse JSON
  const project = JSON.parse(json);

  console.log('\n=== Decoded Project ===');
  console.log('ID:', project.id);
  console.log('Name:', project.metadata?.name);
  console.log('Components:', project.components?.length);
  project.components?.forEach((c, i) => {
    console.log(`  ${i + 1}. ${c.type}: ${c.name}`);
  });
} catch (err) {
  console.error('Error:', err);
  console.error('Stack:', err.stack);
}
