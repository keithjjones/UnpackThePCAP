@load base/frameworks/files
@load base/protocols/http
@load base/files/extract

# Extract every file Zeek sees in an HTTP request body (client -> server).
# Used by scripts/carve.sh: the exfil POST bodies (SCREEN:/FAST_BEACON:/
# HEARTBEAT:) land in extract_files/extract-<ts>-HTTP-<fuid> as-is.
event file_new(f: fa_file)
	{
	if ( f$source == "HTTP" && f$is_orig )
		Files::add_analyzer(f, Files::ANALYZER_EXTRACT);
	}
