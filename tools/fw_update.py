#!/usr/bin/env python
"""
Firmware Updater Tool

A frame consists of two sections:
1. Two bytes for the length of the data section
2. A data section of length defined in the length section

[ 0x02 ]  [ variable ]
--------------------
| Length | Data... |
--------------------

In our case, the data is from one line of the Intel Hex formated .hex file

We write a frame to the bootloader, then wait for it to respond with an
OK message so we can write the next frame. The OK message in this case is
just a zero
"""

import argparse
import pathlib
import struct
import time
import socket

from util import UART0_PATH, UART1_PATH, UART2_PATH, print_hex, DomainSocketSerial

from Crypto.Hash import SHA256
from Crypto.PublicKey import ECC
from Crypto.Signature import DSS
from pwn import *


# size of communication frame
FRAME_SIZE = 256

# size of header
HEADER = 2

# header types
OK = b"O"
ERROR = b"E"
UPDATE = b"U"
BOOT = b"B"
META = b"M"
CHUNK = b"C"
DONE = b"D"


# crypto directory, where keys generated by bl_build are stored
CRYPTO_DIRECTORY = (
    pathlib.Path(__file__).parent.parent.joinpath("bootloader/crypto").absolute()
)


def send_metadata(ser, metadata, debug=False):
    response = None

    print("METADATA:")
    # Parse version information
    version, size = struct.unpack("<HH", metadata[0:4])
    print(f"\tVersion: {version}\n\tSize: {size} bytes\n")

    # Prevent debug abuse
    if version == 0 and not debug:
        raise RuntimeError("Invalid version request, aborting.")

    # Handshake with bootloader to send metadata
    ser.write(META)
    print("\tPacket sent!")
    while ser.read(HEADER) != OK:
        time.sleep()

    print("\tPacket accepted by bootloader!")
    ser.write(metadata)

    print("\tSending metadata!")
    print("\tAwaiting response...")
    
    sleep(0.2)

    b_version = bytes([])
    while len(b_version) != 2:
        b_version = ser.read(2)

    b_version = int(struct.unpack("<H", b_version)[0])
    print(f"\tVersion echoed by bootloader: {b_version}")
    
    sleep(0.2)

    b_size = bytes([])
    while len(b_size) != 2:
        b_size = ser.read(2)

    b_size = int(struct.unpack("<H", b_size)[0])
    print(f"\tVersion size echoed by bootloader: {b_size}")
    
    sleep(0.2)

    b_mlength = bytes([])
    while len(b_mlength) != 2:
        b_mlength = ser.read(2)

    b_mlength = int(struct.unpack("<H", b_mlength)[0])
    print(f"\tMessage length echoed by bootloader: {b_mlength}")

    return True


def send_firmware(ser, firmware, debug=False):
    response = None

    print("FIRMWARE:")

    # Handshake with bootloader to send firmware
    ser.write(CHUNK)
    
    print("\tPacket sent!")
    while ser.read(HEADER) != OK:
        time.sleep()

    print("\tPacket accepted by bootloader!")
    print("\tSending firmware!")

    # Send firmware in frames
    for idx, frame_start in enumerate(range(0, len(firmware), FRAME_SIZE)):
        data = firmware[frame_start : frame_start + FRAME_SIZE]

        # Get length of data
        length = len(data)

        # Construct frame
        frame = struct.pack(f'H{len(data)}s', length, data)

        send_frame(ser, frame, debug=debug)

        print(f"Wrote frame {idx} ({len(frame)} bytes).")
        sleep(0.2)

    
    ser.write(DONE)

    # Send a zero length payload to tell the bootlader to finish writing its page.
    ser.write(struct.pack(">H", 0x0000))

    resp = ser.read(1)  # Wait for an OK from the bootloader
    if resp != OK:
        raise RuntimeError(
            "ERROR: Bootloader responded to zero length frame with {}".format(
                repr(resp)
            )
        )

    print("Done writing firmware.")
    print("Closing update tool.")

    return ser


def send_frame(ser, frame, debug=False):
    ser.write(frame)

    if debug:
        print_hex(frame)

    # Wait for an OK from the bootloader
    time.sleep(0.4)
   
    resp = ser.read(1)
    
    time.sleep(0.2)
  

    if resp != OK:
        raise RuntimeError("ERROR: Bootloader responded with {}".format(repr(resp)))
    if debug:
        print("Resp: {}".format(ord(resp)))


def update(ser, infile, debug):
    # Open serial port. Set baudrate to 115200. Set timeout to 2 seconds.
    with open(infile, "rb") as fp:
        firmware_blob = fp.read()

    response = None

    print("Connected!")
    time.sleep(3)

    print("UPDATE:")
    ser.write(UPDATE)
    print("\tPacket sent!")
    while response != OK:
        response = ser.read(2)

    print("\tPacket accepted by bootloader!\n")

    # Parse firmware blob
    signature = firmware_blob[0:64]
    metadata = firmware_blob[64:70]
    firmware = firmware_blob[70:]

    # Check for integrity compromise using ECC public key signature
    key = None
    with open(CRYPTO_DIRECTORY / "ecc_public.raw", "rb") as fp:
        key = ECC.import_key(fp.read(), curve_name="secp256r1")

    print("\tVerifying firmware data!")
    hasher = SHA256.new(metadata + firmware)
    verifier = DSS.new(key, "fips-186-3")
    try:
        verifier.verify(hasher, signature)
        print("\tHash verified on the client.")
    except ValueError:
        raise RuntimeError("Invalid signature, aborting.")

    ## Proceed to sending data.

    # Send metadata
    print("\tSending metadata!")
    send_metadata(ser, metadata, debug=debug)

    
    send_firmware(ser, firmware, debug=debug)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Firmware Update Tool")

    parser.add_argument(
        "--port",
        help="Does nothing, included to adhere to command examples in rule doc",
        required=False,
    )
    parser.add_argument(
        "--firmware",
        help="Path to firmware image to load.",
        required=False,
        default="../firmware/gcc/main.bin",
    )
    parser.add_argument(
        "--debug", help="Enable debugging messages.", action="store_true"
    )

    args = parser.parse_args()

    uart0_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    uart0_sock.connect(UART0_PATH)

    time.sleep(0.2)  # QEMU takes a moment to open the next socket

    uart1_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    uart1_sock.connect(UART1_PATH)
    uart1 = DomainSocketSerial(uart1_sock)

    time.sleep(0.2)

    uart2_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    uart2_sock.connect(UART2_PATH)

    # Close unused UARTs (if we leave these open it will hang)
    uart2_sock.close()
    uart0_sock.close()

    update(ser=uart1, infile=args.firmware, debug=args.debug)

    uart1_sock.close()
