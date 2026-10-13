##! Detect the Waski trojan downloader via JA4 fingerprints
##!
##! This script detects the Waski downloader documented in
##! Unpack the PCAP episode 3. It generates a notice when:
##!   1. A TLS connection contains JA4 fingerprint t12d190800_d83cc789557e_7af1ed941c26
##!   2. A TLS connection contains JA4 fingerprint t10d070700_c50f5591e341_c39ab67fec8e
##!
##! Uses connection_state_remove to catch connections where TLS handshake failed
##! (e.g., shaf.in where the server never responded).
##!
##! JA4 is preferred over JA3: the human-readable 'a' section (TLS version,
##! cipher count, extension count, ALPN) makes it easier to understand what's
##! unusual about the fingerprint.
##!
##! Usage: zeek -C -r pcap.pcapng ja3 ja4 detect-waski-ja4.zeek
##!
##! Source: https://github.com/keithjjones/UnpackThePCAP

module DetectWaskiJA4;

export {
	redef enum Notice::Type += {
		## JA4 fingerprint matches a known Waski malware client.
		Waski_JA4_Match,
	};
}

# Known Waski JA4 client fingerprints
const waski_ja4s: set[string] = {
	"t12d190800_d83cc789557e_7af1ed941c26",
	"t10d070700_c50f5591e341_c39ab67fec8e",
};

# Use connection_state_remove to catch ALL connections including failed TLS handshakes
event connection_state_remove(c: connection)
{
	if ( ! c?$ssl || ! c$ssl?$ja4 )
		return;

	if ( c$ssl$ja4 in waski_ja4s )
		NOTICE([$note=Waski_JA4_Match,
		        $msg=fmt("Waski JA4 %s from %s -> %s (SNI: %s, established: %s)",
		                 c$ssl$ja4, c$id$orig_h, c$id$resp_h,
		                 c$ssl?$server_name ? c$ssl$server_name : "-",
		                 c$ssl$established ? "T" : "F"),
		        $conn=c,
		        $identifier=cat(c$id$orig_h, c$ssl$ja4)]);
}
