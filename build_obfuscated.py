import os, hashlib, hmac, struct, random, base64

BASE = os.path.dirname(os.path.abspath(__file__))
MODULES = ['license_verify.py', '基础模块.py', '作品采集.py', '博主采集.py', '评论采集.py', 'runner.py']

def _xor_encrypt(data, key):
    result = bytearray()
    for i in range(0, len(data), 32):
        ctr = struct.pack('>QQ', 0, i // 32)
        ks = hmac.new(key, ctr, 'sha256').digest()
        for a, b in zip(data[i:i + 32], ks):
            result.append(a ^ b)
    return bytes(result)

def build():
    seed = os.urandom(32); salt = os.urandom(16); pepper = os.urandom(8)
    iters = 100000 + (sum(pepper) % 50000)
    enc_key = hashlib.pbkdf2_hmac('sha256', seed, salt, iters, dklen=32)
    module_blobs = {}
    for mod_file in MODULES:
        mod_path = os.path.join(BASE, mod_file)
        if os.path.isfile(mod_path):
            with open(mod_path, 'r', encoding='utf-8') as f: source = f.read()
            encrypted = _xor_encrypt(source.encode('utf-8'), enc_key)
            module_blobs[mod_file.replace('.py','')] = base64.b64encode(encrypted).decode('ascii')
            print(f'  [+] {mod_file} -> {len(encrypted)} bytes')

    seed_b64 = base64.b64encode(seed).decode('ascii')
    salt_b64 = base64.b64encode(salt).decode('ascii')
    pepper_b64 = base64.b64encode(pepper).decode('ascii')

    mv = [f'_{random.choice("abcdefghijklmn")}{i:02d}' for i in range(8)]
    fk = f'_{random.choice("uvwxyz")}{random.randint(10,99)}'
    fd = f'_{random.choice("rstuvw")}{random.randint(100,999)}'
    fi = f'_{random.choice("qponml")}{random.randint(10,99)}'
    fx = f'_{random.choice("hijklm")}{random.randint(100,999)}'

    dict_entries = []
    for mn in module_blobs:
        dict_entries.append(f'    "{mn}": "{module_blobs[mn]}",')
    dict_body = '\n'.join(dict_entries)

    guard = f'''"""
XHS Collector v5.0 - Content Collector - Runtime Loader (auto-generated)
"""
import hashlib as {mv[0]}
import hmac as {mv[1]}
import struct as {mv[2]}
import os as {mv[3]}
import sys as {mv[4]}
import base64 as {mv[5]}

if getattr({mv[4]}, 'frozen', False):
    _BD = {mv[3]}.path.dirname({mv[4]}.executable)
else:
    _BD = {mv[3]}.path.dirname({mv[3]}.path.abspath(__file__))

_SEED = {mv[5]}.b64decode("{seed_b64}")
_SALT = {mv[5]}.b64decode("{salt_b64}")
_PEPPER = {mv[5]}.b64decode("{pepper_b64}")

_MODULES = {{
{dict_body}
}}

def {fk}():
    iters = 100000 + (sum(_PEPPER) % 50000)
    return {mv[0]}.pbkdf2_hmac('sha256', _SEED, _SALT, iters, dklen=32)

def {fx}(data, key):
    result = bytearray()
    for i in range(0, len(data), 32):
        ctr = {mv[2]}.pack('>QQ', 0, i // 32)
        ks = {mv[1]}.new(key, ctr, 'sha256').digest()
        for a, b in zip(data[i:i + 32], ks):
            result.append(a ^ b)
    return bytes(result)

def {fd}(name):
    key = {fk}()
    blob_b64 = _MODULES.get(name)
    if not blob_b64: return None
    return {fx}({mv[5]}.b64decode(blob_b64), key).decode('utf-8')

def {fi}():
    for mod_name in _MODULES:
        src = {fd}(mod_name)
        if src is None: continue
        co = compile(src, mod_name + '.py', 'exec')
        mod = type({mv[4]})(mod_name)
        mod.__file__ = {mv[3]}.path.join(_BD, mod_name + '.py')
        {mv[4]}.modules[mod_name] = mod
        exec(co, mod.__dict__)

{fi}()
check_license = {mv[4]}.modules['license_verify'].check_license
get_license_info = {mv[4]}.modules['license_verify'].get_license_info
del _MODULES, _SEED, _SALT, _PEPPER, _BD
'''

    out_path = os.path.join(BASE, '_loader.py')
    with open(out_path, 'w', encoding='utf-8') as f: f.write(guard)
    print(f'[_loader.py] Generated ({len(guard)} chars)')
    return out_path

if __name__ == '__main__':
    build()
