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
import struct
import time

from Crypto.Signature import DSS
from Crypto.Hash import SHA256
from Crypto.PublicKey import ECC
from serial import Serial

RESP_OK = b'\x00'
FRAME_SIZE = 16

TOOL_DIRECTORY = pathlib.Path(__file__).parent.absolute()

def send_metadata(ser, metadata, debug=False):
    # Parse version information
    version, size = struct.unpack_from('<HH', metadata)
    print(f'Request to install version {version}\n')

    # Prevent debug abuse
    if version == 0 and debug == False:
        raise RuntimeError("Invalid version request, aborting.")
        return ser
        
    # Handshake with bootloader for update
    ser.write(b'U')
    print('Waiting for bootloader to enter update mode...')
    while ser.read(1).decode() != 'U':
        pass

    # Invalid version check from bootloader - not working ae
    """old_version = int(ser.read(4).decode());
    if old_version > new_version and debug == False:
        raise RuntimeError("Invalid version request, aborting.")
        return ser"""

    # Send size and version to bootloader.
    if debug:
        print(metadata)
    ser.write(metadata)

    # Wait for an OK from the bootloader.
    resp = ser.read()
    if resp != RESP_OK:
        raise RuntimeError("ERROR: Bootloader responded with {}".format(repr(resp)))

def send_frame(ser, frame, debug=False):

    # Write/optionally print the frame
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
    with open(infile, 'rb') as fp:
        firmware_blob = fp.read()

    # Parse firmware blob
    signature = firmware_blob[0:64] 
    metadata = firmware_blob[64:68]
    firmware = firmware_blob[68:]
    
    # Check for integrity compromise using ECC public key signature
    crypto = TOOL_DIRECTORY / '..' / 'bootloader' / 'crypto'
    f = open(crypto / 'ecc_public.der','rt')
    sigkey = ECC.import_key(f.read())

    h = SHA256.new(metadata + firmware)
    verifier = DSS.new(sigkey, 'fips-186-3')

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
        data = firmware[frame_start: frame_start + FRAME_SIZE]

        # Get length
        length = len(data)
        frame_fmt = '>H{}s'.format(length)
        
        # Construct frame.
        frame = struct.pack(frame_fmt, length, data)

        if debug:
            print("Writing frame {} ({} bytes)...".format(idx, len(frame)))

        send_frame(ser, frame, debug=debug)

    print("Done writing firmware.")

    # Send a zero length payload to tell the bootlader to finish writing its page.
    ser.write(struct.pack('>H', 0x0000))

    return ser


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Firmware Update Tool')

    parser.add_argument("--port", help="Serial port to send update over.",
                        required=True)
    parser.add_argument("--firmware", help="Path to firmware image to load.",
                        required=True)
    parser.add_argument("--debug", help="Enable debugging messages.",
                        action='store_true')
    args = parser.parse_args()

    print('Opening serial port...')
    ser = Serial(args.port, baudrate=115200, timeout=2)
    main(ser=ser, infile=args.firmware, debug=args.debug)


