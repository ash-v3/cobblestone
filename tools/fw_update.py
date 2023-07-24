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

from Crypto.Hash import SHA256
from Crypto.PublicKey import ECC
from Crypto.Signature import DSS
from serial import Serial

RESP_OK = b"\x00"
FRAME_SIZE = 16

OK = struct.pack("<H", 0)
ERROR = struct.pack("<H", 1)
META = struct.pack("<H", 2)
CHUNK = struct.pack("<H", 3)
DONE = struct.pack("<H", 4)

# crypto directory, where keys generated by bl_build are stored
CRYPTO_DIRECTORY = (
    pathlib.Path(__file__).parent.parent.joinpath("bootloader/crypto").absolute()
)


def send_metadata(ser, metadata, debug=False):
    # Parse version information
    version, size = struct.unpack_from("<HH", metadata)
    print(f"Request to install version {version}\n")

    # Prevent debug abuse
    if version == 0 and debug == False:
        raise RuntimeError("Invalid version request, aborting.")
        return ser

    # Handshake with bootloader for update
    ser.write(b"U")
    print("Waiting for bootloader to enter update mode...")
    while ser.read(1).decode() != "U":
        pass

    # Invalid version check from bootloader - not working ae
    """old_version = int(ser.read(4).decode());
    if old_version > new_version and debug == False:
        raise RuntimeError("Invalid version request, aborting.")
        return ser"""

    # Send size and version to bootloader.
    if debug:
        print(metadata)
    ser.write(META)
    ser.write(metadata)

    # Wait for an OK from the bootloader.
    resp = ser.read()
    if resp != RESP_OK:
        raise RuntimeError("ERROR: Bootloader responded with {}".format(repr(resp)))


def send_frame(ser, frame, debug=False):
    # Write/optionally print the frame
    ser.write(CHUNK)
    ser.write(frame)
    if debug:
        print(frame)

    # Wait for an OK from the bootloader
    time.sleep(0.1)
    resp = ser.read()
    time.sleep(0.1)

    if resp != RESP_OK:
        raise RuntimeError("ERROR: Bootloader responded with {}".format(repr(resp)))
    if debug:
        print("Resp: {}".format(ord(resp)))


def main(ser, infile, debug):
    # Open serial port. Set baudrate to 115200. Set timeout to 2 seconds.
    with open(infile, "rb") as fp:
        firmware_blob = fp.read()

    # Parse firmware blob
    signature = firmware_blob[0:64]
    metadata = firmware_blob[64:68]
    firmware = firmware_blob[68:]

    # Check for integrity compromise using ECC public key signature
    f = open(CRYPTO_DIRECTORY / "ecc_public.raw", "rt")
    sigkey = ECC.import_key(f.read())
    h = SHA256.new(metadata + firmware)
    verifier = DSS.new(sigkey, "fips-186-3")
    try:
        verifier.verify(h, signature)
    except ValueError:
        raise RuntimeError("Invalid signature, aborting.")
        return ser

    ## Proceed to sending data.

    # Send metadata
    send_metadata(ser, metadata, debug=debug)

    # Send firmware in frames
    for idx, frame_start in enumerate(range(0, len(firmware), FRAME_SIZE)):
        data = firmware[frame_start : frame_start + FRAME_SIZE]

        # Get length
        length = len(data)
        frame_fmt = ">H{}s".format(length)

        # Construct frame.
        frame = struct.pack(frame_fmt, length, data)

        if debug:
            print("Writing frame {} ({} bytes)...".format(idx, len(frame)))

        send_frame(ser, frame, debug=debug)
    ser.write(DONE)
    print("Done writing firmware.")

    # Send a zero length payload to tell the bootlader to finish writing its page.
    ser.write(struct.pack(">H", 0x0000))

    return ser


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Firmware Update Tool")

    parser.add_argument("--port", help="Does nothing, included to adhere to command examples in rule doc", required=False)
    parser.add_argument("--firmware", help="Path to firmware image to load.", required=False)
    parser.add_argument("--debug", help="Enable debugging messages.", action="store_true")
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
