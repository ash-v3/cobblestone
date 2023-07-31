#!/usr/bin/env python
"""
Firmware Bundle-and-Protect Tool
"""

import argparse
import pathlib
import struct

from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.PublicKey import ECC
from Crypto.Signature import DSS

from Crypto.Util.Padding import pad, unpad

# crypto directory, where keys generated by bl_build are stored
CRYPTO_DIR = (
    pathlib.Path(__file__).parent.parent.joinpath("bootloader/crypto").absolute()
)

# max size of unsigned short
MAX_VERSION = 2**16 - 1
# from challenge outline document (rounded up a bit)
MAX_MESSAGE_SIZE = 1024
MAX_FIRMWARE_SIZE = 32768

# AES-256 key length
AES_KEY_LEN = 32


def protect_firmware(infile, outfile, version, message):
    # Read firmware binary after it is compiled by bl_build
    with open(infile, "rb") as infile:
        firmware = infile.read()

    # check that message and firmware length within project description
    # and that version can be packed as a short
    assert version <= MAX_VERSION
    assert len(message) <= MAX_MESSAGE_SIZE
    assert len(firmware) <= MAX_FIRMWARE_SIZE

    # Extract keys from secret build output 32 bytes AES
    # then ECC private key is the rest of the file
    # Public key not needed for signing; not loaded
    with open(CRYPTO_DIR / "secret_build_output.txt", mode="rb") as secfile:
        aes_key = secfile.read(AES_KEY_LEN)
        priv_key = secfile.read()
        priv_key = ECC.import_key(priv_key)

    # Extract initalization vector (IV) generated by bl_build
    with open(CRYPTO_DIR / "iv.txt", mode="rb") as ivfile:
        iv = ivfile.read()

    # Pack version, length of firmware, and size into 3 little-endian shorts
    # makes 6 byte metadata
    metadata = struct.pack("<HHH", version, len(firmware), len(message))

    # AES-256 cipher, CBC
    aes = AES.new(aes_key, AES.MODE_CBC, iv=iv)

    # ECDSA signer, P-256 curve, for integrity and authenticity
    signer = DSS.new(priv_key, mode="fips-186-3")

    # metadata plus aes of firmware and message, padded and null-terminated
    # sign all of that and prepend signature
    blob = metadata + aes.encrypt(pad(firmware + message.encode() + b"\x00", 16))

    # signs SHA-256 hash
    h = SHA256.new(blob)
    blob = signer.sign(h) + blob

    # write protected firmware blob into outfile
    with open(outfile, "wb") as outfile:
        outfile.write(blob)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Firmware Update Tool")
    parser.add_argument(
        "--infile", help="Path to the firmware image to protect.", required=True
    )
    parser.add_argument(
        "--outfile", help="Filename for the output firmware.", required=True
    )
    parser.add_argument(
        "--version", help="Version number of this firmware.", required=True
    )
    parser.add_argument(
        "--message", help="Release message for this firmware.", required=True
    )
    args = parser.parse_args()
    protect_firmware(
        infile=args.infile,
        outfile=args.outfile,
        version=int(args.version),
        message=args.message
    )

# sus impoter
#                         ▁▃▄▅▆▆▇▇▇▇▆▅▄▃▁
#                      ▁▄▇███████████████▆▖
#                     ▅████████▛▀▀▜████████▙
#                    ▟██████▀▔      ▔▜██████▍
#                   ▐█████▉          ▕██████▍       ▗▃▃▃▃▃▃          ▗▃▃▃▃▃▃             ▂▃▄▄▄▅▅▅▅▄▄▄▃▂
#                   ██████▊                         ██████▊          ▐██████         ▁▄▇████████████████▆▃
#                   ▜██████▙▂▁                     ▕██████▍          ██████▊        ▟████████▛▀▀▀▜████████▙
#                   ▝██████████▇▆▅▄▃▂              ▐██████          ▗██████▍       ▟█████▛▔         ▜██████▏
#                     ▀███████████████▆▃           ██████▊          ▐██████       ▕██████▍           ▔▔▔▔▔▔
#                       ▔▀▀██████████████▖        ▗██████▍          ██████▋       ▕███████▆▅▄▄▃▃▂▂▁▁
#                            ▔▔▔▀▀████████▖       ▟██████          ▐██████▎        ▀█████████████████▇▅▃
#                                  ▀██████▋       ██████▋          ▟██████          ▔▀▜█████████████████▙
#                ▂▂▂▂▂▂             ██████▌      ▐██████▎         ▕██████▋               ▔▔▔▔▀▀▀▀▀███████▋
#               ▐██████▏           ▗██████▏      ▐██████▏         ▟██████▏                         ██████▋
#               ▐██████▙▂        ▂▟██████▘       ▐██████▙       ▂▟██████▘       ▐██████           ▗██████▘
#                ▜████████▆▅▅▅▆▇███████▛▘         ████████▆▅▅▅▆▇███████▘        ▝███████▅▄▄▃▃▃▄▄▅▇██████▘
#                 ▝▜█████████████████▛▘            ▀████████████████▛▀           ▝▜███████████████████▀▔
#                   ▔▀▀▀████████▀▀▀▔                 ▀▀▀███████▛▀▀▔▔               ▔▀▀▜██████████▀▀▀▔
#
#
#                                                     ▁▁▁▁▁▁
#                                              ▂▄▅▆▇███████████▇▇▆▅▄▃▂▁
#                                          ▁▃▆██████████████████████████▇▅▃▁
#                                        ▂▅██████████████████████████████████▅▃
#                                      ▗▆███████████████████████████████████████▆▃
#                                    ▁▟███████████████████████████████████████████▇▃
#                                   ▗███████████████████████████████████████████████▇▖
#                                  ▟██████████████████████████████████████████████████▙
#                                 ▟█████████████████████████████████████████████████████▖
#                                ▟███████████████████████████████████████████████████████▖
#                               ▟█████████████████████████████████████████████████████████▆▄▁
#                              ▟████████████████████████▛▀▀▀▔▔▔▔                   ▔▔▀▀▜█████▆▃
#                             ▗██████████████████████▀▔                                  ▝▜████▙▖
#                             █████████████████████▛                                       ▔▜████▖
#                            ▟█████████████████████▎                                         ▜████▏
#                          ▁▂██████████████████████                                           ████▋
#                ▂▃▃▄▅▆▇▇██████████████████████████▏                                          ▐████▏
#            ▅▆▇███████████████████████████████████▎                                          ▕████▍
#          ▗███████████████████████████████████████▋                                          ▕████▍
#          ▟████████████████████████████████████████▖                                         ▐████▏
#         ▟██████████████████████████████████████████▄                                       ▗████▋
#        ▗█████████████████████████████████████████████▅▃▁                                  ▅████▛
#        █████████████████████████████████████████████████▇▆▅▄▃▂▁▁                     ▁▂▄▆█████▘
#       ▐███████████████████████████████████████████████████████████▇▇▇▆▆▆▆▆▆▆▆▆▆▆▆▇▇█████████▛
#       ▟█████████████████████████████████████████████████████████████████████████████████████▌
#       ██████████████████████████████████████████████████████████████████████████████████████▍
#      ▕██████████████████████████████████████████████████████████████████████████████████████▎
#      ▐██████████████████████████████████████████████████████████████████████████████████████▏
#      ▐██████████████████████████████████████████████████████████████████████████████████████
#      ▐█████████████████████████████████████████████████████████████████████████████████████▉
#      ▐█████████████████████████████████████████████████████████████████████████████████████▊
#      ▐█████████████████████████████████████████████████████████████████████████████████████▌
#      ▕█████████████████████████████████████████████████████████████████████████████████████▍
#      ▕█████████████████████████████████████████████████████████████████████████████████████▏
#       █████████████████████████████████████████████████████████████████████████████████████
#       ▜███████████████████████████████████████████████████████████████████████████████████▊
#       ▐███████████████████████████████████████████████████████████████████████████████████▌
#       ▕███████████████████████████████████████████████████████████████████████████████████▎
#        ▜██████████████████████████████████████████████████████████████████████████████████
#        ▐█████████████████████████████████████████████████████████████████████████████████▋
#         █████████████████████████████████████████████████████████████████████████████████▍
#         ▝████████████████████████████████████████████████████████████████████████████████▏
#          ▔▀█████████████████████████████████████████████████████████████████████████████▊
#             ▔▀▀▀▜██████▀▀▜██████████████████████████████████████████████████████████████▌
#                           ██████████████████████████████▔▔▔▔▔▔▜█████████████████████████▏
#                           ▜████████████████████████████▉      ▐████████████████████████▊
#                           ▐████████████████████████████▊      ▕████████████████████████▍
#                           ▕████████████████████████████▋       ████████████████████████
#                            ▜███████████████████████████▌       ▐██████████████████████▋
#                            ▝███████████████████████████▍       ▐██████████████████████▎
#                             ███████████████████████████▎       ▕█████████████████████▊
#                             ▝██████████████████████████▏        ████████████████████▀▘
#                                ▔▔▀▀▀▀▀▀▀▜██▛▀▀▀▀▀▀▀▔▔           ▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔
