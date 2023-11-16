#!~/.pyenv/boostzapper/bin/python3
import botutils as utils
import sys

if __name__ == '__main__':

    if len(sys.argv) <= 1:
        print("No npub or hex value provided")
        quit()

    if sys.argv[1].startswith("n"):
        h = utils.normalizeToHex(sys.argv[1])
        print(f"Decoded hex: {h}")
        quit()
    
    if utils.isHex(sys.argv[1]):
        if len(sys.argv) <= 2:
            print(f"Human readable prefix not provided")
            quit()
        else:
            n = utils.normalizeToBech32(sys.argv[1], sys.argv[2])
            print(f"Bech32 encoded: {n}")
    else:
        print(f"Value was not detected as hex or bech32")
