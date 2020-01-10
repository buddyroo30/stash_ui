#!/usr/bin/env perl

use strict;
use warnings;
use JSON;
use CGI;

my $allKeysFile = "all_jira_keys.json";

my $q = CGI->new();

my $callback = $q->param("callback");
if (!defined($callback) || ($callback =~ m/^\s*$/)) {
    undef $callback;
}
my $searchTxt = $q->param("search_text");

my $resultsArr = searchJira($searchTxt);

print "Access-Control-Allow-Origin: *\nContent-Type: application/json\n\n";
if (defined($callback)) {
    print "${callback}(";
}
print to_json( { 'success' => JSON::true, 'results' => $resultsArr } );
if (defined($callback)) {
    print ");";
}
exit 0;

sub searchJira {

    my ($searchTxt) = @_;

    my @allJiraKeysArr;
    if (-f $allKeysFile) {
	my $allJiraKeysJsonTxt = slurp_file($allKeysFile); #should really do some kind of lock on this file first
	my $allJiraKeys = from_json($allJiraKeysJsonTxt);
	@allJiraKeysArr = keys %$allJiraKeys;
    }

    my @results = sort grep { m/${searchTxt}/i; } @allJiraKeysArr;

    return(\@results);

}


sub slurp_file {

    my ($filePath) = @_;

    open my $fh, '<', $filePath or die "Error opening $filePath to read: $!";
    my $oldVal = $/;
    $/ = undef;
    my $data = <$fh>;
    close $fh;
    $/ = $oldVal;

    return($data);
}

sub empty {

    my ($str) = @_;

    if (!defined($str) || ($str =~ m/^\s*$/)) { return 1; }

    return 0;
}
