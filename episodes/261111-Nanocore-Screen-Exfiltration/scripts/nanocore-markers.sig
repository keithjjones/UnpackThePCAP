# NanoCore-family plaintext HTTP POST marker protocol — Unpack the PCAP episode 4
#
# Pattern type is `http-request-body`, NOT `payload`: payload-type patterns
# only see a bounded early window of the TCP stream (measured against this
# capture: bytes 0..1523 matched, 1524+ never tested), which misses
# markers past the first screenshot body. `http-request-body` is fed every
# request-body chunk live at any offset, the type itself declares the
# POST-body context, and bol anchors `^` at the start of the body — where
# this family puts its marker.
#
# Anchor on the LABEL, never the payload shape: the encoding after the
# colon is data, not protocol (PNG/hex/raw variants break payload-shape
# patterns; notes.md has the full analysis). The anchor does the FP work —
# benign POST bodies start '{' (JSON), 'key=' (form), '--' (multipart),
# '<' (XML), never an uppercase LABEL at byte 0. Format classification
# lives in the DuckDB layer; the full body rides in the Notice $sub as
# evidence.
#
# CLIP: never fires on episode 4's capture (no clipboard activity in the
# sandbox) but is observed in sibling samples — keep it so clipboard runs
# do not slip through.
#
# The payload after the colon rotates per victim (Environment.MachineName) —
# match on the marker, never on the hostname.

signature nanocore-screen {
	ip-proto == tcp
	http-request-body /^SCREEN:/
	eval NanoCore::screen_match
}

signature nanocore-fast-beacon {
	ip-proto == tcp
	http-request-body /^FAST_BEACON:/
	eval NanoCore::fast_beacon_match
}

signature nanocore-heartbeat {
	ip-proto == tcp
	http-request-body /^HEARTBEAT:/
	eval NanoCore::heartbeat_match
}

signature nanocore-clip {
	ip-proto == tcp
	http-request-body /^CLIP:/
	eval NanoCore::clip_match
}
