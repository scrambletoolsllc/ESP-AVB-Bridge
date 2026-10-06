#!/usr/bin/env python3
"""Send one bench-only capability indication to the bridge's wired decoder.

Uses the host's own identity. Does not receive or sniff traffic; capture with
Wireshark tools separately. This tests decoding, not neighbor capability.
"""
import json
from pathlib import Path
import socket
import struct
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tools'))
import atdecc_controller as controller
interface = 'nic1'
source = controller.get_mac_address(interface)
destination = bytes.fromhex('80f1b2d2caa9')
message = bytearray(60)
message[0:5] = bytes([0x1c, 2, 0, 60, 0])
message[20:28] = controller.mac_to_entity_id(source)
message[28:30] = struct.pack('!H', 99)
message[30:34] = bytes([0x59, 1, 5, 0x7f])
message[34:44] = bytes.fromhex('80f1b2fffed2caa90001')
message[44:60] = bytes([0x80,0,0,12,0,0x80,0xc2,0,0,4,0,0,0,0,0,0])
frame = destination + source + struct.pack('!H', 0x88f7) + message
with socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x88f7)) as sender:
    sender.bind((interface, 0))
    sent = sender.send(frame)
    if sent != len(frame): raise RuntimeError('Short send')
print(json.dumps({'interface': interface, 'source': source.hex(),
    'destination': destination.hex(), 'bytes': sent, 'ptp_hex': message.hex()}))
