##! Detection for the NanoCore marker protocol (episode 4).
##!
##! nanocore-markers.sig carries four signatures with the `http-request-body`
##! pattern type (SCREEN:, FAST_BEACON:, HEARTBEAT:, CLIP:); matching runs
##! in Zeek's C++ signature engine against request-body bytes, and these
##! evals do nothing but raise a Notice with the matched payload as
##! evidence. See the .sig for the measured pattern-type analysis.
##!
##! Usage (from the episode root):
##!
##!   zeek -C -r <pcap> scripts/
##!
##! Source: https://github.com/keithjjones/UnpackThePCAP

module NanoCore;

export {
	redef enum Notice::Type += {
		## An HTTP POST carries a known NanoCore-family C2 marker
		## (SCREEN:, FAST_BEACON:, HEARTBEAT:, CLIP:).
		C2_Traffic_Observed,
	};
}

# Shared notice raiser, AgentTesla style: marker + endpoints in msg,
# matched payload in sub as evidence.
function notice_marker(c: connection, marker: string, data: string)
	{
	NOTICE([$note=NanoCore::C2_Traffic_Observed,
	        $msg=fmt("NanoCore-family C2 marker '%s' in HTTP request from %s to %s:%d",
	                 marker, c$id$orig_h, c$id$resp_h, c$id$resp_p),
	        $sub=data,
	        $conn=c]);
	}

function screen_match(state: signature_state, data: string): bool &is_used
	{
	notice_marker(state$conn, "SCREEN:", data);
	return T;
	}

function fast_beacon_match(state: signature_state, data: string): bool &is_used
	{
	notice_marker(state$conn, "FAST_BEACON:", data);
	return T;
	}

function heartbeat_match(state: signature_state, data: string): bool &is_used
	{
	notice_marker(state$conn, "HEARTBEAT:", data);
	return T;
	}

function clip_match(state: signature_state, data: string): bool &is_used
	{
	notice_marker(state$conn, "CLIP:", data);
	return T;
	}
