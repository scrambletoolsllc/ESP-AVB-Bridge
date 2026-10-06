# FTM FollowUp codec

`components/ftm_follow_up` supplies a portable reference encoder/parser for
one 82-byte vendor IE containing a 76-byte gPTP FollowUp. It is not connected
to the radio callback or endpoint servo yet, and is not IRAM audited.

The relay encoder preserves the upstream precise origin, domain, flags and
time-base/phase/frequency-change metadata. The caller supplies the outgoing
sourcePortIdentity, sequence, interval, cumulative rate offset, and additional
correction in signed 2^-16 ns units. Correction addition rejects overflow and
retains fractional nanoseconds. It does not manufacture a new origin from
the current clock or replace upstream time-base information with zeroes.

The parser checks the IE identifier, length, OUI/type, gPTP header, message
length, information TLV and representable timestamp. This implementation
supports exactly the base 76-byte FollowUp and an int64 nanosecond epoch;
additional TLVs and larger epochs are rejected. A successful parse does not
establish source selection, freshness, asCapable or valid FTM association.
Those remain explicit responsibilities of the transport state machine.

Before callback integration:

- Carry coherent source and mapping snapshots over SDIO, bound to both boot
  identities and a validated hardware edge. Expire on source loss/change.
- Calculate the added residence/path correction in BTC units, using the
  actual transmit timestamp and the matching upstream observation.
- Associate each FollowUp with the driver's followup token, including initial
  frames, retries, token rollover, peer changes and source changes mid-burst.
- Match Announce and FollowUp sourcePortIdentity. The current beacon path
  substitutes BTC identity; the Announce path copies an upstream header.
  They can coincide in this bench topology, but are not a complete relay.
- Audit the linked callback path for IRAM/DRAM residency, bounded arithmetic
  and no library calls that access flash. The reference codec is task code.
- Explicitly invalidate a fixed-length callback payload on failure. The codec
  leaves output unchanged on failure; the driver may still transmit its
  registered fixed IE length. Never reuse a previous valid IE accidentally.

Tests in `tools/ftm_bridge_clock/test_follow_up.c` use a wire fixture with
nonzero domain, negative fractional correction and time-base metadata.
They check byte layout, metadata retention, truncation, malformed headers,
signed limits and unchanged output on failure under ASan/UBSan.

Preliminary format cross-check: [IEEE P802.1AS-Rev D8, clause 12.7](https://1.ieee802.org/wp-content/uploads/2019/03/802-1AS-rev-d8-0.pdf).
This unapproved draft is not the final conformance authority; final 2020
edition and corrections, negotiation and state-machine requirements remain
open as recorded in `ftm-conformance-gaps.md`.
