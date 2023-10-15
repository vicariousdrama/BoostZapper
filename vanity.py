#!/usr/bin/env python3
from nostr.key import PrivateKey

lookfor = "jess"
lookfor = "23456789"

# not supported:  b i o 1
# a e u 
if not set(lookfor).issubset(set('acdefghjklmnpqrstuvwxyz987654320')):
  print(f"lookfor ({lookfor}) contains values not supported in bech32")
  quit()
while True:
  k = PrivateKey()
  s = k.public_key.bech32()
  if f"npub1{lookfor}" in s:
    print(k.bech32())
    print(s)
    quit()
