##! Detect the Polish "Powiadomienie" JS Campaign
##!
##! This script detects the credential theft campaign documented in
##! Unpack the PCAP episode 2. It generates a notice when:
##!   1. A workstation makes an HTTP request to ip-api.com with
##!      the anti-sandbox parameter /line/?fields=hosting
##!   2. A workstation queries DNS for the C2 domain ftp.telewatte-pe.com
##!   3. An FTP STOR command matches the credential exfiltration pattern
##!
##! Usage: zeek -C -r pcap.pcap detect-powiadomienie.zeek
##!
##! Source: https://github.com/keithjjones/UnpackThePCAP

module DetectPowiadomienie;

export {
	redef enum Notice::Type += {
		## An HTTP request to ip-api.com with the `fields=hosting` parameter,
		## indicating an anti-sandbox / environment check.
		HTTP_IpApi_HostingCheck,

		## A DNS query for the known C2 domain ftp.telewatte-pe.com.
		DNS_C2_Domain,

		## An FTP STOR command with a filename matching the credential
		## exfiltration pattern PW_<user>-<hostname>_<timestamp>.html
		FTP_Credential_Exfil,
	};
}

# Global regex constants — compiled once, not per event
const ip_api_uri_re = /\/line\/\?fields=hosting/;
const exfil_file_re = /^PW_.+\.html$/;

# Detect the anti-sandbox HTTP request to ip-api.com
# http_all_headers fires after all headers are received, so
# c$http$uri (from http_request) and c$http$host are both set.
event http_all_headers(c: connection, is_orig: bool, hlist: mime_header_list)
{
	if ( ! is_orig )
		return;

	if ( c$http?$host && c$http$host == "ip-api.com" &&
	     c$http?$uri && ip_api_uri_re in c$http$uri )
		NOTICE([$note=HTTP_IpApi_HostingCheck,
		        $msg=fmt("Host %s made anti-sandbox request: GET %s",
		                 c$id$orig_h, c$http$uri),
		        $conn=c]);
}

# Detect DNS queries for the known C2 domain
event dns_request(c: connection, msg: dns_msg, query: string, qtype: count, qclass: count)
{
	if ( query == "ftp.telewatte-pe.com" )
		NOTICE([$note=DNS_C2_Domain,
		        $msg=fmt("Host %s queried known C2 domain: %s",
		                 c$id$orig_h, query),
		        $conn=c]);
}

# Detect FTP STOR matching the exfil pattern
event ftp_request(c: connection, command: string, arg: string)
{
	if ( command == "STOR" && exfil_file_re in arg )
		NOTICE([$note=FTP_Credential_Exfil,
		        $msg=fmt("Credential exfil via FTP: %s %s",
		                 command, arg),
		        $conn=c]);
}
