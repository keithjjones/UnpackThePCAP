##! Detect the Waski trojan downloader via TLS SNI
##!
##! This script detects the Waski downloader documented in
##! Unpack the PCAP episode 3. It generates a notice when:
##!   1. A TLS Client Hello contains SNI for packaging-labelling.com
##!   2. A TLS Client Hello contains SNI for www.packaging-labelling.com
##!   3. A TLS Client Hello contains SNI for shaf.in
##!
##! Uses connection_state_remove to catch connections where the TLS handshake
##! failed but the SNI was still present in the Client Hello (e.g., shaf.in
##! where the server never responded).
##!
##! Usage: zeek -C -r pcap.pcapng ja3 ja4 detect-waski-sni.zeek
##!
##! Source: https://github.com/keithjjones/UnpackThePCAP

module DetectWaskiSNI;

export {
	redef enum Notice::Type += {
		## TLS SNI matches a known Waski payload delivery or callback domain.
		Waski_SNI_Match,
	};
}

# Known malicious SNI values
const waski_snis: set[string] = {
	"packaging-labelling.com",
	"www.packaging-labelling.com",
	"shaf.in",
};

# Use connection_state_remove to catch ALL connections including failed TLS handshakes
event connection_state_remove(c: connection)
{
	if ( ! c?$ssl || ! c$ssl?$server_name )
		return;

	local sni = to_lower(c$ssl$server_name);

	if ( sni in waski_snis )
		NOTICE([$note=Waski_SNI_Match,
		        $msg=fmt("Waski Downloader SNI: %s -> %s",
		                 c$id$orig_h, sni),
		        $conn=c,
		        $identifier=cat(c$id$orig_h, c$id$resp_h, sni)]);
}
