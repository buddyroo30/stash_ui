#!/usr/bin/env perl

BEGIN {
  require './Config.pl';
}

use strict;
use warnings;
use JSON;
use CGI;
use Net::LDAP;

my $ldapServer = $Config::ldapServer;
my $ldap_bindDn = $Config::ldap_bindDn;
my $ldap_searchBase = $Config::ldap_searchBase;
my $ldap_searchFilter = $Config::ldap_searchFilter;
my $ldap_searchScope = $Config::ldap_searchScope;
my $ldapFieldMap = $Config::ldapFieldMap;

my $q = CGI->new();

my $callback = $q->param("callback");
if (!defined($callback) || ($callback =~ m/^\s*$/)) {
    undef $callback;
}

my $searchTxt = $q->param("term");
if (empty($searchTxt)) {
    $searchTxt = $q->param("search_text");
}

my $jqa = $q->param("jqa"); #For Jquery Autocomplete (if so then just return results array)

my ($succ,$resultsArr) = searchLdap($searchTxt);

print "Access-Control-Allow-Origin: *\nContent-Type: application/json\n\n";
if (defined($callback)) {
    print "${callback}(";
}
if (!$succ) {
    if (defined($jqa) && ($jqa eq '1')) {
	print to_json([]);
    } else {
	print to_json( { 'success' => JSON::false, 'msg' => $resultsArr } );
    }
} else {
    if (defined($jqa) && ($jqa eq '1')) {
	print to_json($resultsArr);
    } else {
	print to_json( { 'success' => JSON::true, 'results' => $resultsArr } );
    }
}
if (defined($callback)) {
    print ");";
}
exit 0;

sub searchLdap {

    my ($searchTxt) = @_;

    if (empty($searchTxt)) { $searchTxt = ''; }

    my $server = $ldapServer;

    my $results = [];

    # Connect to LDAP server
    my $ldap = Net::LDAP->new($server);
    my $linfo = $ldap->bind(dn => $ldap_bindDn);

    my $ldap_searchFilter_copy = $ldap_searchFilter;
    $ldap_searchFilter_copy =~ s/__SEARCH_TEXT__/${searchTxt}/g;

    my $msg = $ldap->search(base => $ldap_searchBase,
			    filter => $ldap_searchFilter_copy,
			    scope => $ldap_searchScope);
    $ldap->unbind;
    return (0,"Error getting LDAP attrs for search '$searchTxt'") if ! $msg;
    return (0,"Error getting attrs for search '$searchTxt'\n" . $msg->error) if $msg->code;

#    die("No match!") if ! $msg->count;

    foreach my $entry ($msg->entries) {
	#$entry->dump;
	my $mail = $entry->get_value($ldapFieldMap->{'mail'});
	my $cn = $entry->get_value($ldapFieldMap->{'cn'});
	my $uid = $entry->get_value($ldapFieldMap->{'uid'});
	my $uid_cn = "${cn} (${uid})";
	push @$results, { 'userid' => $uid, 'cn' => $cn, 'userid_cn' => $uid_cn, 'email' => $mail,
	                  'value' => $uid_cn, 'label' => $uid_cn };
    }

    return (1,$results);

}

sub empty {

    my ($str) = @_;

    if (!defined($str) || ($str =~ m/^\s*$/)) { return 1; }

    return 0;
}
