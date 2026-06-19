"""{proj['name']} License Key Generator — Developer Tool"""
import hashlib, hmac, struct, time, os, sys

_SECRET_SEED = b'XHSCollector2026Secret!#'
_SECRET_SALT = b'XHSCollectorSalt2026#'
_HMAC_SALT_1 = hashlib.sha256(b'enc_v2_st' + _SECRET_SEED).digest()[:16]
_HMAC_SALT_2 = hashlib.sha256(b'auth_v2_st' + _SECRET_SEED).digest()[:16]
CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'

def _derive_keys():
    master = hashlib.pbkdf2_hmac('sha256', _SECRET_SEED, _SECRET_SALT, 200_000, dklen=64)
    return (hmac.new(master[:32], _HMAC_SALT_1, 'sha256').digest(),
            hmac.new(master[32:], _HMAC_SALT_2, 'sha256').digest())

def _hmac_ctr(data, key, nonce):
    result = bytearray()
    for i in range(0, len(data), 32):
        ctr = struct.pack('>QQ', nonce, i // 32)
        ks = hmac.new(key, ctr, 'sha256').digest()
        for a, b in zip(data[i:i + 32], ks): result.append(a ^ b)
    return bytes(result)

def _b32e(data):
    bits = bit_len = 0; result = []
    for b in data:
        bits = (bits << 8) | b; bit_len += 8
        while bit_len >= 5: bit_len -= 5; result.append(CROCKFORD[(bits >> bit_len) & 0x1F])
    if bit_len > 0: result.append(CROCKFORD[(bits << (5 - bit_len)) & 0x1F])
    return ''.join(result)

def _customer_id(name):
    return struct.unpack('>H', hashlib.sha256(name.encode()).digest()[:2])[0]

def generate(days, customer):
    expire_ts = 0xFFFFFFFF if days == 0 else int(time.time()) + days * 86400
    cid = _customer_id(customer)
    payload = struct.pack('>BIH8s', 1, expire_ts, cid, b'\x00' * 8)
    enc_key, auth_key = _derive_keys()
    nonce = int.from_bytes(os.urandom(2), 'big')
    ciphertext = _hmac_ctr(payload, enc_key, nonce)
    combined = struct.pack('>H', nonce) + ciphertext
    sig = hmac.new(auth_key, b'\x01' + combined, 'sha256').digest()[:6]
    encoded = _b32e(combined + sig)
    while len(encoded) < 26: encoded = '0' + encoded
    return 'XHC1-' + encoded

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: python 密钥.py <days> <customer>'); print('  0 days = permanent')
        customer = input('Customer name: ').strip()
        if not customer: sys.exit(1)
        try: days = int(input('Days (0=permanent): ').strip())
        except: sys.exit(1)
    else:
        days, customer = int(sys.argv[1]), sys.argv[2]
    key = generate(days, customer)
    with open('license.key', 'w', encoding='utf-8') as f:
        f.write(key + '\n' + customer + '\n')
    print(f'License saved: {customer} | {"Permanent" if days==0 else str(days)+"d"}')
    if len(sys.argv) < 3: input('Press Enter to exit...')
