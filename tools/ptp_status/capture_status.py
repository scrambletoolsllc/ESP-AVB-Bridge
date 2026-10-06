#!/usr/bin/env python3
"""Query source identity/path across a finite clock observation-loss test."""
import argparse
import datetime
import json
from pathlib import Path
import struct
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tools'))
import atdecc_controller as controller
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
parser.add_argument('--interface', default='nic1')
parser.add_argument('--entity', default='fc:01:2c:fd:fe:80:00:00')
parser.add_argument('--seconds', type=int, default=85)
args = parser.parse_args()
if not 1 <= args.seconds <= 180: parser.error('duration outside diagnostic limit')
sock, mac, controller_id, entity, destination = controller._aem_cli_setup(args.interface, args.entity)
sequence = int(time.monotonic() * 1000) & 0xffff
records = []
def query(command, body):
    global sequence
    sequence = (sequence + 1) & 0xffff
    message = (controller.encode_atdecc_header(controller.AVTP_SUBTYPE_AECP,
        controller.AECP_MSG_AEM_COMMAND, 0, 0, 0, 20 + len(body)) + entity +
        controller_id + struct.pack('!H', sequence) +
        controller.encode_aecp_aem_header(command) + body)
    controller.send_frame(sock, args.interface, destination, mac, message)
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        result = controller.recv_frame(sock, timeout=.1)
        if result is None: continue
        _, payload = result
        if len(payload) < 24: continue
        subtype, kind, _, _, status, _ = controller.decode_atdecc_header(payload[:4])
        if (subtype != controller.AVTP_SUBTYPE_AECP or kind != controller.AECP_MSG_AEM_RESPONSE
            or payload[4:12] != entity or payload[12:20] != controller_id
            or int.from_bytes(payload[20:22], 'big') != sequence
            or (int.from_bytes(payload[22:24], 'big') & 0x7fff) != command): continue
        return status, payload
    return None
try:
    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        row = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        reply = query(0x27, struct.pack('!HH', controller.AEM_DESC_TYPE_AVB_INTERFACE, 0))
        if reply is None: row['avb_info_timeout'] = True
        else:
            status, payload = reply
            row['avb_info_status'] = status
            row['avb_info_hex'] = payload.hex()
            if status == 0 and len(payload) >= 44:
                row.update(btc=payload[28:36].hex(), domain=payload[40], flags=payload[41])
        reply = query(0x28, struct.pack('!HH', 0, 0))
        if reply is None: row['path_timeout'] = True
        else:
            status, payload = reply
            row['path_status'] = status
            row['path_hex'] = payload.hex()
            if status == 0 and len(payload) >= 28:
                count = int.from_bytes(payload[26:28], 'big')
                if len(payload) >= 28 + count * 8:
                    row['path'] = [payload[28+index*8:36+index*8].hex() for index in range(count)]
        records.append(row)
        args.output.write_text(json.dumps(records, indent=2) + '\n')
        time.sleep(.3)
finally:
    sock.close()
print(json.dumps({'records': len(records), 'output': str(args.output)}))
