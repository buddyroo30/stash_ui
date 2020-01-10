#!/usr/bin/env perl

use strict;
use warnings;
use JSON;
use CGI;
use DBI;
use DBD::Oracle qw(:ora_types);

setOracleEnvParams();
my $q = CGI->new();

my $ldapDbh = getDbh("tbiop1.cbe7mtbvwi2d.us-east-1.rds.amazonaws.com",
		     "TBIOP1",
		     1521,
		     "ldap",
		     "ldap123");

my $callback = $q->param("callback");
if (!defined($callback) || ($callback =~ m/^\s*$/)) {
    undef $callback;
}
my $searchTxt = $q->param("search_text");

my $resultsArr = searchLdap($ldapDbh, $searchTxt);

$ldapDbh->disconnect();

print "Access-Control-Allow-Origin: *\nContent-Type: application/json\n\n";
if (defined($callback)) {
    print "${callback}(";
}
print to_json( { 'success' => JSON::true, 'results' => $resultsArr } );
if (defined($callback)) {
    print ");";
}
exit 0;

sub searchLdap {

    my ($dbh, $searchTxt) = @_;

    my $results = [];

    $searchTxt = lc($searchTxt);

    my $sql = "select userid, GIVENNAME || ' ' || SN AS cn, GIVENNAME || ' ' || SN || ' (' || userid || ')' AS userid_cn from ldappeople";
    if (!empty($searchTxt)) {
	$sql = "select userid, cn, userid_cn from (" . $sql . ") where lower(userid_cn) like '%${searchTxt}%'";
    }

    my $sth = $dbh->prepare($sql) ||
	die("Error preparing stmt: " . $DBI::errstr);
    $sth->execute() ||
	die("Error executing stmt: " . $DBI::errstr);
    while (my @row = $sth->fetchrow_array()) {
	my ($userid,$cn,$userid_cn) = @row;
	push @$results, { 'userid' => $userid, 'cn' => $cn, 'userid_cn' => $userid_cn };
    }
    $sth->finish;

    return($results);

}

sub empty {

    my ($str) = @_;

    if (!defined($str) || ($str =~ m/^\s*$/)) { return 1; }

    return 0;
}

sub getDbh {

    my ($hostname, $sid, $port, $userid, $passwd) = @_;


    my $dbh = DBI->connect("DBI:Oracle:host=$hostname;sid=$sid;port=$port", $userid, $passwd,
			   { AutoCommit => 0,
			     RaiseError => 1 });

    if (!$dbh) {
	die "Error creating dbh in getDbh: " . $DBI::errstr . "\n";
    }


    return($dbh);
}


sub setOracleEnvParams {

    $ENV{'ORACLE_HOME'} = $ENV{'ORACLE_HOME'}  || "/u01/home/oracle/product/11.1";
    $ENV{'ORACLE_ADMIN'} = $ENV{'ORACLE_ADMIN'}  || "/u01/home/oracle/admin";
    $ENV{'ORACLE_BASE'} = $ENV{'ORACLE_BASE'}  || "/u01/home/oracle";

}
