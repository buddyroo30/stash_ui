#!/usr/bin/env perl

BEGIN {
  require './Config.pl';
}

use strict;
use warnings;
#use Data::Dumper;
#use MIME::Base64;
use CGI;
use Getopt::Long;
use JSON;
use URI::Escape;
#use POSIX;
use File::Temp qw/ tempfile /;
use File::Basename;
use Net::LDAP;
#Download SendMail (and other stuff) like this:
#curl -o perlscr-master.zip https://codeload.github.com/ivanamihalek/perlscr/zip/master
#NOTE: modify line 721 of SendMail.pm to get rid of warning
use lib "/var/www/cgi-bin/domrep/perl_mods/perlscr-master/SendMail-2.09";
use SendMail;
use lib "/var/www/cgi-bin/domrep/perl_mods/installed/lib/perl5";
use Net::OpenSSH;

#process exit codes
use constant EX_SUCC => 0;
use constant EX_FAIL => 1;
use constant EX_WARN => 2;
use constant EX_FTL  => 3;

use constant RETRY_SSH_CNT  => 1;

my $thisScriptName = basename($0);
my $thisScriptFullUrl = CGI::url();
my $thisScriptDomain = '';
if ($thisScriptFullUrl =~ m/^\s*([a-zA-Z]+\:\/\/[^\/]+)/) { $thisScriptDomain = $1; }
my $stashUIFullUrl = "${thisScriptDomain}/stash_ui_release/stash_ui/index.html";

my $fsSelTxt = "<SELECT style='width:100%' NAME='fs'>\n" . join("\n",map { my $selTxt = ($_ eq 'default') ? 'SELECTED ' : '';
							"<OPTION ${selTxt}value='${_}'>${_}</OPTION>"; } keys %$Config::managedFileSystems) .
	       "</SELECT>\n";

my $allUsersWebAccessGroup = "EVERYONE"; #special web-access only group that signifies all users

#0 if the script is called as a CGI script (e.g. by Apache), 1 otherwise (e.g. command line execution)
my $nocgi = $ENV{HTTP_HOST} ? 0 : 1;

setProxyEnvVars();

my $q = CGI->new();

my $a;
my $fs;
my $stage;
my $mode;
my $dirPath;
my $targetPath;
my $base;
my $eacl;
my $webeacl;
my $filePath;
my $disposition;
my $shareUsers;
my $recursive;
my $directFilePath;
my $stashFileName;
my $newPath;
my $user;
my $no_email;
my $current_user;
my $search_ug_fs_or_web;
my $search_ug_user_or_group;
my $search_ug_search_text;
my $user_sshkey;
my $user_password;
my $callback;

my $singleQuoteInPathsFlag = 0;

setParams();

if (empty($fs)) { $fs = "default"; }
my $fsConfig = $Config::managedFileSystems->{$fs};
if (!defined($fsConfig)) { cgi_die_json("Error: there is no file system '${fs}' being managed"); }

my ($fsRoot, $fsHost, $fsPort, $fsSetCurrentUser, $fsUser, $fsKeyfile) =
    ($fsConfig->{"root"},$fsConfig->{"host"},$fsConfig->{"port"},$fsConfig->{"set_current_user"},
     $fsConfig->{"user"},$fsConfig->{"keyfile"});
if (!defined($fsRoot)) { cgi_die_json("Error: managed file system '${fs}' has no root."); }

if (!empty($fsSetCurrentUser)) { $current_user = $fsSetCurrentUser; }

if (empty($current_user)) {
    cgi_die_json("Error: must be authenticated user.");
}

my $fs_users; my $fs_groups;

if (empty($a)) { $a = "show_actions"; }
if (empty($stage)) { $stage = 'form'; }

#admin mode not used now, but could potentially use it somehow if wanted.
if (empty($mode) || (($mode ne 'user') && ($mode ne 'admin'))) { $mode = 'user'; }
if (($mode eq 'admin') && !$Config::adminUsers->{$current_user}) { $mode = 'user'; }

my $actionFuncs = { 'show_actions' => \&show_actions,
		    'test_ssh_key' => { 'form' => \&TestSshKey_form, 'exec' => \&TestSshKey },
		    'download_file' => { 'form' => \&DownloadFile_form, 'exec' => \&DownloadFile },
		    'download_dir' => { 'form' => \&DownloadDir_form, 'exec' => \&DownloadDir },
		    'stash_file' => { 'form' => \&StashFile_form, 'exec' => \&StashFile },
		    'create_dir' => { 'form' => \&CreateDir_form, 'exec' => \&CreateDir },
		    'create_symlink' => { 'form' => \&CreateSymlink_form, 'exec' => \&CreateSymlink },
		    'directory_contents' => { 'form' => \&DirectoryContents_form, 'exec' => \&DirectoryContents },
		    'show_eacl' => { 'form' => \&ShowEacl_form, 'exec' => \&ShowEacl },
		    'modify_eacl' => { 'form' => \&ModifyEacl_form, 'exec' => \&ModifyEacl },
		    'share' => { 'form' => \&Share_form, 'exec' => \&Share },
		    'determine_user_access' => { 'form' => \&DetermineUserAccess_form, 'exec' => \&DetermineUserAccess_svc },
		    'move' => { 'form' => \&Move_form, 'exec' => \&Move },
		    'delete' => { 'form' => \&Delete_form, 'exec' => \&Delete },
		    'get_current_user' => \&getCurrentUser_svc,
		    'check_zip_access' => \&checkZipAccess_svc,
		    'search_ug' => \&searchUg };

my $curActionFuncs = $actionFuncs->{$a};
if (!defined($curActionFuncs)) {
    cgi_die_json("Error: bad action '$a'");
} else {
    if (ref $curActionFuncs eq 'HASH') {
	my $actualActionFunc = $curActionFuncs->{$stage};
	if (!defined($actualActionFunc)) {
	    cgi_die_json("Error: bad stage '${stage}' for action '${a}'");
	}
	$actualActionFunc->();
    } else {
	$curActionFuncs->();
    }
}

exit 0;

sub setProxyEnvVars {

    $ENV{'https_proxy'} = 'http://proxy-server:8080';
    $ENV{'http_proxy'}  = 'http://proxy-server:8080';
    $ENV{'ftp_proxy'}   = 'http://proxy-server:8080';
    $ENV{'no_proxy'}    = 'bms.com,localhost,169.254.169.254';
    $ENV{'HTTPS_PROXY'} = 'http://proxy-server:8080';
    $ENV{'HTTP_PROXY'}  = 'http://proxy-server:8080';
    $ENV{'FTP_PROXY'}   = 'http://proxy-server:8080';

}

sub show_actions {

    printHeader();

    print <<EOF;
<html>
<body>
<center><h3>RR Simple Stash</h3></center>
<ul>
<li><a href='${thisScriptName}?a=test_ssh_key'>TestSshKey</a>
<li><a href='${thisScriptName}?a=download_file'>DownloadFile</a>
<li><a href='${thisScriptName}?a=download_dir'>DownloadDir</a>
<li><a href='${thisScriptName}?a=stash_file'>StashFile</a>
<li><a href='${thisScriptName}?a=create_dir'>CreateDir</a>
<li><a href='${thisScriptName}?a=create_symlink'>CreateSymlink</a>
<li><a href='${thisScriptName}?a=directory_contents'>DirectoryContents</a>
<li><a href='${thisScriptName}?a=show_eacl'>ShowEacl</a>
<li><a href='${thisScriptName}?a=modify_eacl'>ModifyEacl</a>
<li><a href='${thisScriptName}?a=share'>Share</a>
<li><a href='${thisScriptName}?a=determine_user_access'>DetermineUserAccess</a>
<li><a href='${thisScriptName}?a=move'>Move</a>
<li><a href='${thisScriptName}?a=delete'>Delete</a>
</ul>
<hr><a href='${thisScriptName}'>home</a>
</body>
</html>
EOF

}

sub checkZipAccess_svc {

    my ($hasZipAccessFlag, $zipErrMsg) = checkZipAccess($dirPath);

    printHeader('application/json');
    my $retObj = { 'success' => JSON::true,
		   'has_zip_access' => $hasZipAccessFlag ? JSON::true : JSON::false };

    if (!empty($zipErrMsg) && !$hasZipAccessFlag) {
	$retObj->{'msg'} = $zipErrMsg;
    }
    print to_json($retObj);

}

sub getCurrentUser_svc {

    printHeader('application/json');
    my $retObj = { 'success' => JSON::true,
		   'current_user' => $current_user };
    print to_json($retObj);

}

sub CreateDir_form {

    printHeader();

    print <<EOF;
<html>
<head><title>CreateDir</title>
<style>
#createdir {
    font-family: "Trebuchet MS", Arial, Helvetica, sans-serif;
    border-collapse: collapse;
    width: 100%;
}

#createdir td, #createdir th {
    border: 1px solid #ddd;
    padding: 8px;
}

#createdir tr:nth-child(even){background-color: #f2f2f2;}

#createdir tr:hover {background-color: #ddd;}

#createdir th {
    padding-top: 12px;
    padding-bottom: 12px;
    text-align: left;
    background-color: #004851;
    color:  #8D9093;
}

</style>
</head>
<body>
<center><h3>CreateDir</h3></center>
Create a new directory path (relative to the root directory) and specify the users and groups who can access the directory as base access (standard Linux user/group/other) and/or extended ACL. Note that 2 versions of extended ACL can be specified, one for web-based access and one for filesystem based access; the web-based extended ACL grants access only through these web services and it is optional. For example create path <i>results/my_project/prod1</i> with base access of <i>u:smitha26:rwx,g:xpress:r,o:OTHER:r</i> (which will set the owner to smitha26 and the group to xpress), filesystem extended ACL of <i>g:bioinfo:r,u:russom:rw</i> and web-based extended ACL of <i>u:john:r</i>. You must have write access (via filesystem ACL; web-based extended ACL is only considered and used for read operations) to the directory path, or you will get an error response. For example, if you specify to create directory <i>results/my_proj/proj_data</i> and <i>results/my_proj</i> exists but you do not have write access to it, then you will receive an error response. If the full path to the directory does not exist it will be created as necessary (i.e. basically a 'mkdir -p PATH' will be done) with each created path segment having base access of the uploading user having 'rwx' access. However, you must have write access to the nearest existing parent directory or you will get an error response. Note that there is also a special web-access only group called EVERYONE that you can use to specify that any user can access, e.g. EVERYONE:r means any user accessing the system has read access to the directory. Choose the Filesystem you want to work with (the system can be configured to manage multiple file systems). An SSH private key or the user's password must be provided in order to have file system extended ACL considered (otherwise only web-access extended ACL will be considered) and is required for any write operations like this service.
<form method='POST' enctype='multipart/form-data' action='${thisScriptName}'>
<table id="createdir"><tr><th>INPUT</th><th>INPUT VALUE</th></tr>
<tr><td>Directory Path:</td><td><input style="width:100%" type=text name=dir_path /></td></tr>
<tr><td>Base ACL (File System):</td><td><input style="width:100%" type=text name=base /></td></tr>
<tr><td>Extended ACL (File System):</td><td><input style="width:100%" type=text name=eacl /></td></tr>
<tr><td>Extended ACL (Web Access):</td><td><input style="width:100%" type=text name=webeacl /></td></tr>
<tr><td>Filesystem:</td><td>${fsSelTxt}</td></tr>
<tr><td>Password:</td><td><input style="width:100%" type=text name=user_password /></td></tr>
<tr><td>SSH Private Key:</td><td><textarea style="width:100%" rows=3 id=user_sshkey name=user_sshkey></textarea></td></tr>
</table><p>
<input type=submit value=Exec />
<input type=hidden name=a value=create_dir />
<input type=hidden name=stage value=exec />
</form>
<hr><a href='${thisScriptName}'>home</a>
</body>
</html>
EOF

}

sub ShowEacl_form {

    printHeader();

    print <<EOF;
<html>
<head><title>ShowEacl</title>
<style>
#showeacl {
    font-family: "Trebuchet MS", Arial, Helvetica, sans-serif;
    border-collapse: collapse;
    width: 100%;
}

#showeacl td, #showeacl th {
    border: 1px solid #ddd;
    padding: 8px;
}

#showeacl tr:nth-child(even){background-color: #f2f2f2;}

#showeacl tr:hover {background-color: #ddd;}

#showeacl th {
    padding-top: 12px;
    padding-bottom: 12px;
    text-align: left;
    background-color: #004851;
    color:  #8D9093;
}

</style>
</head>
<body>
<center><h3>ShowEacl</h3></center>
Retrieve the current extended ACL (i.e. users and groups who can access, and whether they can 'read', 'write', or 'execute') for a specified relative directory or file path (relative to the root), for example <i>results/my_project/prod1</i>. Both filesystem and web-based access extended ACL will be returned. You must have read access to the parent directory in order to view the extended ACL (except anyone can view for the root). Leave the path blank to show the extended ACL for the root directory. Choose the Filesystem you want to work with (the system can be configured to manage multiple file systems, both local or remote). An SSH private key or the user's password must be provided in order to have file system extended ACL considered (otherwise only web-access extended ACL will be considered) and is required for any write operations.
<form method='POST' enctype='multipart/form-data' action='${thisScriptName}'>
<table id="showeacl"><tr><th>INPUT</th><th>INPUT VALUE</th></tr>
<tr><td>Dir or File Path:</td><td><input style="width:100%" type=text name=dir_path /></td></tr>
<tr><td>Filesystem:</td><td>${fsSelTxt}</td></tr>
<tr><td>Password:</td><td><input style="width:100%" type=text name=user_password /></td></tr>
<tr><td>SSH Private Key:</td><td><textarea style="width:100%" rows=3 id=user_sshkey name=user_sshkey></textarea></td></tr>
</table><p>
<input type=submit value=Exec />
<input type=hidden name=a value=show_eacl />
<input type=hidden name=stage value=exec />
</form>
<hr><a href='${thisScriptName}'>home</a>
</body>
</html>
EOF

}

sub ShowEacl {

    if (empty($dirPath)) { #empty means the root directory of simple_stash, normalize to simple empty string
	$dirPath = "";
    } else {
	$dirPath =~ s/\/+$//;
    }

    if ($dirPath =~ m/^\//) {
	cgi_die_json("Error in ShowEacl: The path must be a relative path (not absolute), with no leading \/ character. Files are stashed relative to the stash root of $fsRoot");
    }

    my $canReadFlag = 0;
    my ($pathInfo_full_info, $pathInfo, $pathInfo_fs_user);

    if (empty($dirPath)) { #root
	$canReadFlag = 1;
	($pathInfo_full_info, $pathInfo, $pathInfo_fs_user) = pathInfo([$dirPath],0);
    } else {

	my ($dirPathPar, $dirPathLastPart) = parentPath($dirPath);
	if (!defined($dirPathPar)) {
	    cgi_die_json("Error in ShowEacl: could not extract parent directory from '${dirPath}'");
	}
	
	($pathInfo_full_info, $pathInfo, $pathInfo_fs_user) = pathInfo([$dirPath,$dirPathPar],0);
	
	if ($pathInfo_full_info->{'paths_info'}{$dirPath}{'doesnt_exist'}) {
	    cgi_die_json("Error in ShowEacl: path '${dirPath}' does not exist.", { 'path_exists' => JSON::false });
	}

	if (defined($pathInfo) && $pathInfo->{'paths_info'}{$dirPathPar}{'permissions'}{'x'}) { #can view ACL
	    $canReadFlag = 1;
	} else { #check webeacl (i.e. web access rules)
	    my $webPerms = determineWebPerms($pathInfo_full_info->{'paths_info'}{$dirPathPar}{'webeacl'});
	    if ($webPerms->{'r'}) {
		$canReadFlag = 1;
	    }
	}
    }

    if (!$canReadFlag) {
        cgi_die_json("Error in ShowEacl: access denied to path '${dirPath}'");
    }

    my $theDirFsAcl = $pathInfo_full_info->{'paths_info'}{$dirPath}{'eacl'};
    my $theDirWebAcl = $pathInfo_full_info->{'paths_info'}{$dirPath}{'webeacl'};

    my $_eacl_str = eacl_hash_to_str($theDirFsAcl->{'extended_perms'});
    my $_webeacl_str = eacl_hash_to_str($theDirWebAcl);

    my $base_acl_hash = { 'u' => { $theDirFsAcl->{'owner'} => $theDirFsAcl->{'owner_perms'} },
			  'g' => { $theDirFsAcl->{'group'} => $theDirFsAcl->{'group_perms'} },
			  'o' => { 'OTHER' => $theDirFsAcl->{'other_perms'} } };

    my $_base_str = eacl_hash_to_str($base_acl_hash);

    printHeader('application/json');
    my $retObj = { 'success' => JSON::true, 'msg' => "Successfully got eACL of path $dirPath",
		   'base' => $_base_str,
		   'eacl' => $_eacl_str,
		   'webeacl' => $_webeacl_str,
		   'directory_exists' => JSON::true,
		   'read_access' => JSON::true };
    print to_json($retObj);

}

sub Delete_form {

    printHeader();

    print <<EOF;
<html>
<head><title>Delete</title>
<style>
#delete {
    font-family: "Trebuchet MS", Arial, Helvetica, sans-serif;
    border-collapse: collapse;
    width: 100%;
}

#delete td, #delete th {
    border: 1px solid #ddd;
    padding: 8px;
}

#delete tr:nth-child(even){background-color: #f2f2f2;}

#delete tr:hover {background-color: #ddd;}

#delete th {
    padding-top: 12px;
    padding-bottom: 12px;
    text-align: left;
    background-color: #004851;
    color:  #8D9093;
}

</style>
</head>
<body>
<center><h3>Delete</h3></center>
Delete a specified relative file or directory path (relative to the root), for example delete file <i>results/my_project/prod1/out_tmp.txt</i>. You must have write access to the specified directory or file path's parent or you will receive an error response. Choose the Filesystem you want to work with (the system can be configured to manage multiple file systems, both local or remote). An SSH private key or the user's password must be provided in order to have file system extended ACL considered (otherwise only web-access extended ACL will be considered) and is required for any write operations like this service.
<form method='POST' enctype='multipart/form-data' action='${thisScriptName}'>
<table id="delete"><tr><th>INPUT</th><th>INPUT VALUE</th></tr>
<tr><td>Dir or File Path:</td><td><input style="width:100%" type=text name=dir_path /></td></tr>
<tr><td>Filesystem:</td><td>${fsSelTxt}</td></tr>
<tr><td>Password:</td><td><input style="width:100%" type=text name=user_password /></td></tr>
<tr><td>SSH Private Key:</td><td><textarea style="width:100%" rows=3 id=user_sshkey name=user_sshkey></textarea></td></tr>
</table><p>
<input type=submit value=Exec />
<input type=hidden name=a value=delete />
<input type=hidden name=stage value=exec />
</form>
<hr><a href='${thisScriptName}'>home</a>
</body>
</html>
EOF

}

sub userProvidedCredentials {

    if (empty($user_sshkey) && empty($user_password)) {
	return 0;
    } else {
	return 1;
    }
}

sub Delete {

    if (!userProvidedCredentials()) {
	cgi_die_json("Error in Delete: write operations are only allowed via a user's credentials (SSH private key or password), please provide.");
    }

    if (empty($dirPath)) { #empty means the root directory of simple_stash, you can't change its eacl
	cgi_die_json("Error in Delete: you cannot delete the root directory.", { 'path_exists' => JSON::true, 'write_access' => JSON::false });
    }

    if ($dirPath =~ m/^\//) {
	cgi_die_json("Error in Delete: The path must be a relative path (not absolute), with no leading \/ character. Files are stashed relative to the stash root of $fsRoot");
    }


    $dirPath =~ s/\/+$//;

    my ($dirPathPar, $dirPathLastPart) = parentPath($dirPath);
    if (!defined($dirPathPar)) {
        cgi_die_json("Error in Delete: could not parse $dirPath");
    }

    #To delete a file, you need at least 'wx' access to it's parent dir
    #and at least 'x' access to all higher level dirs. You do not need any
    #permissions on the file itself. To delete a directory, you will need the
    #same permissions as just specified for a file, but in addition you'll need
    #the correct permissions to delete any underlying files and dirs of the
    #directory (i.e. 'wx' on the parent dir and 'x' for all higher level dirs).

    my ($pathInfo_full_info, $pathInfo, $pathInfo_fs_user) = pathInfo([$dirPath,$dirPathPar],1);

    if ($pathInfo_full_info->{'paths_info'}{$dirPath}{'doesnt_exist'}) {
       cgi_die_json("Error in Delete: path '${dirPath}' does not exist.", { 'path_exists' => JSON::false });
    }

    if (!defined($pathInfo) || !($pathInfo->{'paths_info'}{$dirPathPar}{'permissions'}{'w'} &&
	                         $pathInfo->{'paths_info'}{$dirPathPar}{'permissions'}{'x'})) { #access denied to delete
        cgi_die_json("Error in Delete: access denied to path '${dirPath}'");
    }

    if ($pathInfo_full_info->{'paths_info'}{$dirPath}{'type'} eq 'D') { #need to make sure you have access to delete lower level content

	my ($allPathsDown, $errMsg) = allPathsUnder($dirPath);
	if (!defined($allPathsDown)) {
	    return (0,"Error in Delete: couldn't get all paths under '${dirPath}': $errMsg");
	}

#	my ($pathInfo_full_info, $pathInfo, $pathInfo_fs_user)
	my @pathInfoResArr = pathInfo($allPathsDown,0);

	my ($hasPerm, $permDownErrMsg) = checkAccessUnder($dirPath,\@pathInfoResArr,undef,{ 'fs' => ['w','x'] });
	if (!$hasPerm) { cgi_die_json("Error in Delete: you do not have access to delete '${dirPath}': $permDownErrMsg"); }
    }

    delPath($dirPath);

    printHeader('application/json');
    my $retObj = { 'success' => JSON::true, 'msg' => "Successfully deleted path '${dirPath}'",
		   'path_exists' => JSON::true,
		   'delete_access' => JSON::true };
    print to_json($retObj);

}

sub TestSshKey_form {

    printHeader();

    print <<EOF;
<html>
<head><title>TestSshKey</title>
<style>
#testsshkey {
    font-family: "Trebuchet MS", Arial, Helvetica, sans-serif;
    border-collapse: collapse;
    width: 100%;
}

#testsshkey td, #testsshkey th {
    border: 1px solid #ddd;
    padding: 8px;
}

#testsshkey tr:nth-child(even){background-color: #f2f2f2;}

#testsshkey tr:hover {background-color: #ddd;}

#testsshkey th {
    padding-top: 12px;
    padding-bottom: 12px;
    text-align: left;
    background-color: #004851;
    color:  #8D9093;
}

</style>
</head>
<body>
<center><h3>Test SSH Key</h3></center>
This service will simply test your provided credentials (SSH private key or password) to see if it works on the host of your chosen file system.
<form method='POST' enctype='multipart/form-data' action='${thisScriptName}'>
<table id="testsshkey"><tr><th>INPUT</th><th>INPUT VALUE</th></tr>
<tr><td>Filesystem:</td><td>${fsSelTxt}</td></tr>
<tr><td>Password:</td><td><input style="width:100%" type=text name=user_password /></td></tr>
<tr><td>SSH Private Key:</td><td><textarea style="width:100%" rows=3 id=user_sshkey name=user_sshkey></textarea></td></tr>
</table><p>
<input type=submit value=Exec />
<input type=hidden name=a value=test_ssh_key />
<input type=hidden name=stage value=exec />
</form>
<hr><a href='${thisScriptName}'>home</a>
</body>
</html>
EOF

}

sub TestSshKey {

    if (!userProvidedCredentials()) {
	cgi_die_json("Error in TestSshKey: please provide credentials (SSH private key or password) to test.");
    }

    my $simpleEchoCmd = "echo 'works'";

    my $retVal = evalOrDie({"cmd" => $simpleEchoCmd,
			    "dont_die" => 1,
			    "parseJsonFlag" => 0,
			    "msgIfErr" => "Error testing private SSH key."});

    my $retRes = rem_ws($retVal->{'res'});
    if ($retRes eq 'works') {
	my $retObj = { 'success' => JSON::true, 'msg' => "Provided credentials tested successfully and work.",
		       'ssh_key_works' => JSON::true };

	printHeader('application/json');	
	print to_json($retObj);
    } else {
	my $dieErrMsg = "Error: your provided credentials did not work, please check and update it and try again.";
	cgi_die_json($dieErrMsg, { 'ssh_key_works' => JSON::false, %$retVal });
    }

}


sub ModifyEacl_form {

    printHeader();

    print <<EOF;
<html>
<head><title>ModifyEacl</title>
<style>
#modifyeacl {
    font-family: "Trebuchet MS", Arial, Helvetica, sans-serif;
    border-collapse: collapse;
    width: 100%;
}

#modifyeacl td, #modifyeacl th {
    border: 1px solid #ddd;
    padding: 8px;
}

#modifyeacl tr:nth-child(even){background-color: #f2f2f2;}

#modifyeacl tr:hover {background-color: #ddd;}

#modifyeacl th {
    padding-top: 12px;
    padding-bottom: 12px;
    text-align: left;
    background-color: #004851;
    color:  #8D9093;
}

</style>
</head>
<body>
<center><h3>ModifyEacl</h3></center>
Modify the base access (standard Linux user/group/other), filesystem and/or web-based access extended ACL (i.e. users and groups who can access, and whether they can '<b>r</b>ead', '<b>w</b>rite', or 'e<b>x</b>ecute') for a specified relative file or directory path (relative to the root), for example for path <i>results/my_project/prod1</i> set the base access to <i>u:smitha26:rwx,g:xpress:r,o:OTHER:r</i> (which will set the owner to smitha26 and the group to xpress), the filesystem extended ACL to <i>g:bioinfo:r,u:russom:r</i> and the web-based extended ACL to <i>g:EVERYONE:r</i>. You must be the owner of the specified directory or file path, or you will receive an error response. Note that there is also a special web-access only group called EVERYONE that you can use to specify that any user can access, e.g. EVERYONE:rw means any user accessing the system can read or write the file or directory. Choose the Filesystem you want to work with (the system can be configured to manage multiple file systems, both local or remote). Also, specify whether you want to modify recursively (i.e. the specified path and all its sub paths and sub files) or only modify the specified path; for recursive you will also need to be the owner of all sub paths and sub files or will receive an error response. An SSH private key or the user's password must be provided in order to have file system extended ACL considered (otherwise only web-access extended ACL will be considered) and is required for any write operations like this service.
<form method='POST' enctype='multipart/form-data' action='${thisScriptName}'>
<table id="modifyeacl"><tr><th>INPUT</th><th>INPUT VALUE</th></tr>
<tr><td>Dir or File Path:</td><td><input style="width:100%" type=text name=dir_path /></td></tr>
<tr><td>Base ACL (File System):</td><td><input style="width:100%" type=text name=base /></td></tr>
<tr><td>Extended ACL (File System):</td><td><input style="width:100%" type=text name=eacl /></td></tr>
<tr><td>Extended ACL (Web Access):</td><td><input style="width:100%" type=text name=webeacl /></td></tr>
<tr><td>Filesystem:</td><td>${fsSelTxt}</td></tr>
<tr><td>Recursive?</td><td><select name=recursive>
<option selected value="0">No</option>
<option value="1">Yes</option>
</select></td></tr>
<tr><td>Password:</td><td><input style="width:100%" type=text name=user_password /></td></tr>
<tr><td>SSH Private Key:</td><td><textarea style="width:100%" rows=3 id=user_sshkey name=user_sshkey></textarea></td></tr>
</table><p>
<input type=submit value=Exec />
<input type=hidden name=a value=modify_eacl />
<input type=hidden name=stage value=exec />
</form>
<hr><a href='${thisScriptName}'>home</a>
</body>
</html>
EOF

}

sub resetEaclAndDie {

    my ($backupAclTxt, $backupWebAclTxt, $dieErrMsg) = @_;

    my $recursTxt = " recursively";
    if (!$recursive) { $recursTxt = ""; }

    if (empty($dieErrMsg)) {
	$dieErrMsg = "There was an error setting filesystem and/or web ACL, and so they have been reset back to their original values.";
    }

    if (defined($backupWebAclTxt)) {
	evalOrDie({"cmd" => "setfattr --restore -",
		   "stdin_data" => $backupWebAclTxt,
		   "parseJsonFlag" => 0,
		   "msgIfErr" => $dieErrMsg . "\n\nError restoring web eacl for $dirPath to original values in resetEaclAndDie${recursTxt}"});
    }

    if (defined($backupAclTxt)) {
	evalOrDie({"cmd" => "setfacl --restore=-",
		   "stdin_data" => $backupAclTxt,
		   "parseJsonFlag" => 0,
		   "msgIfErr" => $dieErrMsg . "\n\nError restoring eacl for $dirPath to original values in resetEaclAndDie${recursTxt}"});
    }

    cgi_die_json($dieErrMsg);

}

sub ModifyEacl {

    my ($justReturnFlag) = @_; #if true, don't print out JSON reply, just return

    my $findNotRecurs = " -maxdepth 0";
    if ($recursive) { $findNotRecurs = ""; }
    my $faclRecurs = " -R";
    if (!$recursive) { $faclRecurs = ""; }
    my $recursTxt = " recursively";
    if (!$recursive) { $recursTxt = ""; }

    if (!userProvidedCredentials()) {
	cgi_die_json("Error in ModifyEacl: write operations are only allowed via a user's credentials (SSH private key or password), please provide.");
    }

    if (empty($dirPath)) { #empty means the root directory of simple_stash, you can't change its eacl
	cgi_die_json("Error in ModifyEacl: you cannot modify the eACL of the root directory.", { 'path_exists' => JSON::true, 'write_access' => JSON::false });
    }

    if ($dirPath =~ m/^\//) {
	cgi_die_json("Error in ModifyEacl: The path must be a relative path (not absolute), with no leading \/ character. Files are stashed relative to the stash root of $fsRoot");
    }

    $dirPath =~ s/\/+$//;

    my $fullPath = $fsRoot . "/" . $dirPath;

    my ($dirPathPar, $dirPathLastPart) = parentPath($dirPath);
    if (!defined($dirPathPar)) {
	cgi_die_json("Error in ModifyEacl: could not extract parent directory from '${dirPath}'");
    }

    my ($pathInfo_full_info, $pathInfo, $pathInfo_fs_user) = pathInfo([$dirPath,$dirPathPar],0);

    if ($pathInfo_full_info->{'paths_info'}{$dirPath}{'doesnt_exist'}) {
       cgi_die_json("Error in ModifyEacl: path '${dirPath}' does not exist.", { 'path_exists' => JSON::false });
    }

    if (!defined($pathInfo) || !$pathInfo->{'paths_info'}{$dirPathPar}{'permissions'}{'x'}) { #access denied to modify acl
        cgi_die_json("Error in ModifyEacl: access denied to path '${dirPath}'");
    }

    my $base_hash = eacl_str_to_hash($base);
    my ($base_is_valid, $base_err_msg) = check_base_access($base_hash);
    if (!$base_is_valid) {
	cgi_die_json("Error: Base access '${base}' is not valid: $base_err_msg");
    }
    my $base_for_setfacl = eacl_hash_to_str($base_hash, 1);

    my $findCmd = 'find \'' . $fullPath . '\' ' . $findNotRecurs . ' -exec sh -c \'getfacl -p "$1" ; chmod u+rwx "$1"\' sh {} \;';
    my $retVal = evalOrDie({"cmd" => $findCmd,
			    "dont_die" => 1,
			    "success_exit" => { 0 => 1 },
			    "parseJsonFlag" => 0,
			    "msgIfErr" => "Error getting current ACLs and setting to u+rwx for ${dirPath}${recursTxt}"});

    my $origSavedAcl = $retVal->{'res'};
    my $retErrMsg = $retVal->{'err_msg'};
    my $stderr_contents = $retVal->{'stderr'};
    if (!empty($stderr_contents)) {
	if ($stderr_contents =~ m/No such file or directory/s) {
	    cgi_die_json("Error in ModifyEacl: path $dirPath does not exist.", { 'path_exists' => JSON::false });
	}
    }

    if (($stderr_contents =~ m/Permission denied/s) ||
	($stderr_contents =~ m/Operation not permitted/)) {
	    cgi_die_json("Error in ModifyEacl: only the owner can modify a file or directory's eACL and you are not the owner of $dirPath and its sub-content and so cannot modify extended ACL${recursTxt}.",
			 { 'path_exists' => JSON::true, 'write_access' => JSON::false });
    }

    giveFsUserAccess($dirPath);

    $retVal = evalOrDie({"cmd" => "getfattr${faclRecurs} -d --absolute-names '${fullPath}'",
			 "parseJsonFlag" => 0,
			 "msgIfErr" => "Error getting web eacl for $dirPath${recursTxt} in ModifyEacl"});
    my $origSavedFattr = $retVal->{'res'};

    my $retResFattr;
    my $retErrMsgFattr;
    my $retStderrFattr;
    if (empty($webeacl)) { #remove
	my $retVal = evalOrDie({"cmd" => "find '${fullPath}'${findNotRecurs} -exec setfattr -x user.webeacl '{}' \\;",
				"dont_die" => 1,
				"success_exit" => { 0 => 1 },
				"parseJsonFlag" => 0,
				"msgIfErr" => "Error removing webeacl for $dirPath in modifyEacl${recursTxt}"});

	$retResFattr = $retVal->{'res'};
	$retErrMsgFattr = $retVal->{'err_msg'};
	$retStderrFattr = $retVal->{'stderr'};
    } else {
	my $retVal = evalOrDie({"cmd" => "find '${fullPath}'${findNotRecurs} -exec setfattr -n user.webeacl -v '${webeacl}' '{}' \\;",
				"dont_die" => 1,
				"success_exit" => { 0 => 1 },
				"parseJsonFlag" => 0,
				"msgIfErr" => "Error doing setfattr for webeacl for $dirPath in modifyEacl${recursTxt}"});

	$retResFattr = $retVal->{'res'};
	$retErrMsgFattr = $retVal->{'err_msg'};
	$retStderrFattr = $retVal->{'stderr'};
    }

    if (!empty($retErrMsgFattr) || ($retStderrFattr =~ m/Permission denied/)) { #calls to setfattr failed, so set back to original value
	my $resetEaclAndDieMsg = "Error setting web ACL for $dirPath in ModifyEacl${recursTxt}, resetting back to original values.";
	if ($Config::DEBUG) {
	    $resetEaclAndDieMsg .= "\nerr_msg:\n${retErrMsgFattr}\nstderr:\n${retStderrFattr}\n";
	}
	resetEaclAndDie(undef, $origSavedFattr, $resetEaclAndDieMsg);
    }

    my $eacl_hash = eacl_str_to_hash($eacl);
    delete $eacl_hash->{'u'}{$fsUser}; #don't let user modify any extended ACL for $fsUser
    #but just add in rx priviliges for $fsUser as extended ACL
    $eacl_hash->{'u'}{$fsUser} = { 'r' => 1, 'x' => 1 };
    $eacl = eacl_hash_to_str($eacl_hash);

    my $base_group_hash = $base_hash->{'g'} || {};
    my @base_group_arr = keys %$base_group_hash;
    if (@base_group_arr) {
	my $base_group = $base_group_arr[0];
	evalOrDie({ 'cmd' => "chgrp${faclRecurs} ${base_group} '${fullPath}'",
		    'parse_json_flag' => 0,
		    'msgIfErr' => "Error setting base group to '${base_group}' for '${dirPath}'${recursTxt}"});
	
    }

    evalOrDie({"cmd" => "setfacl${faclRecurs} -b '$fullPath'",
	       "parseJsonFlag" => 0,
	       "msgIfErr" => "Error resetting file system eacl to empty for $dirPath in ModifyEacl${recursTxt}"});

    my $set_access_str;
    if (!empty($eacl) && !empty($base_for_setfacl)) {
	$set_access_str = $eacl . "," . $base_for_setfacl;
    } elsif (!empty($eacl)) {
	$set_access_str = $eacl;
    } elsif (!empty($base_for_setfacl)) {
	$set_access_str = $base_for_setfacl;
    }
    my $setFaclCmd = 'find \'' .  $fullPath . '\'' . $findNotRecurs . ' -depth -exec setfacl -m ' . $set_access_str . ' \'{}\' \;'; #need to do bottom up (from leaves up the hierarchy)
    my $retValSetfacl = evalOrDie({"cmd" => $setFaclCmd,
				   "dont_die" => 1,
				   "success_exit" => { 0 => 1 },
				   "parseJsonFlag" => 0,
				   "msgIfErr" => "Error setting file system eacl for $dirPath in ModifyEacl${recursTxt}"});

    my $retResSetfacl = $retValSetfacl->{'res'};
    my $retErrMsgSetfacl = $retValSetfacl->{'err_msg'};

    if (defined($retErrMsgSetfacl)) { #call to setfacl failed, so set back to original value
	resetEaclAndDie($origSavedAcl, $origSavedFattr, "Error setting file system eacl for $dirPath in ModifyEacl${recursTxt}, resetting back to original values");
    }

    my $retObj = { 'success' => JSON::true, 'msg' => "Successfully modified eACL of path ${dirPath}${recursTxt}",
		   'path_exists' => JSON::true,
		   'write_access' => JSON::true };

    if ($justReturnFlag) {
	return($retObj);
    } else {
	printHeader('application/json');	
	print to_json($retObj);	
    }

}

sub Share_form {

    printHeader();

    print <<EOF;
<html>
<head><title>Share</title>
<style>
#share {
    font-family: "Trebuchet MS", Arial, Helvetica, sans-serif;
    border-collapse: collapse;
    width: 100%;
}

#share td, #share th {
    border: 1px solid #ddd;
    padding: 8px;
}

#share tr:nth-child(even){background-color: #f2f2f2;}

#share tr:hover {background-color: #ddd;}

#share th {
    padding-top: 12px;
    padding-bottom: 12px;
    text-align: left;
    background-color: #004851;
    color:  #8D9093;
}

</style>
</head>
<body>
<center><h3>Share</h3></center>
Share a directory or file (<b>Dir or File Path</b>) with other users (whose LDAP usernames are passed comma separated in <b>Share Users</b>). The users will be given read web access (if they do not already have it) and then an email will be sent to them informing of the directory or file being shared (with links to view or download it). Also, specify whether you want to give read web access recursively (i.e. the specified path and all its sub paths and sub files) or only for the specified path. You must be the owner of the specified directory or file path (and of all sub paths and sub files for directories), or you will receive an error response. An SSH private key or the user's password must be provided in order to have file system extended ACL considered (otherwise only web-access extended ACL will be considered) and is required for any write operations like this service.
<form method='POST' enctype='multipart/form-data' action='${thisScriptName}'>
<table id="share"><tr><th>INPUT</th><th>INPUT VALUE</th></tr>
<tr><td>Dir or File Path:</td><td><input style="width:100%" type=text name=dir_path /></td></tr>
<tr><td>Share Users:</td><td><input style="width:100%" type=text name=share_users /></td></tr>
<tr><td>Filesystem:</td><td>${fsSelTxt}</td></tr>
<tr><td>Recursive?</td><td><select name=recursive>
<option selected value="0">No</option>
<option value="1">Yes</option>
</select></td></tr>
<tr><td>Password:</td><td><input style="width:100%" type=text name=user_password /></td></tr>
<tr><td>SSH Private Key:</td><td><textarea style="width:100%" rows=3 id=user_sshkey name=user_sshkey></textarea></td></tr>
</table><p>
<input type=submit value=Exec />
<input type=hidden name=a value=share />
<input type=hidden name=stage value=exec />
</form>
<hr><a href='${thisScriptName}'>home</a>
</body>
</html>
EOF

}

#Give the file system, e.g. irods, user rx access down the tree and also up the tree, so can
#access files based on web access rules on behalf of users
sub giveFsUserAccess {

    my ($dirPath) = @_;

    my $fullPath = $fsRoot . "/" . $dirPath;

    my $retVal2 =
    evalOrDie({"cmd" => "setfacl -R -m u:${fsUser}:rx '$fullPath'",
	       "parseJsonFlag" => 0,
	       "msgIfErr" => "Error giving $fsUser file system user access to $dirPath"});

    my $parentDir = dirname($fullPath);
    while (1) {
	last if (($parentDir =~ m/^\/\s*$/) || empty($parentDir));
	my $retVal = evalOrDie({"cmd" => "setfacl -m u:${fsUser}:rx '$parentDir'",
				"parseJsonFlag" => 0,
				"dont_die" => 1,
				"msgIfErr" => "Error giving $fsUser file system user access to $dirPath"});
	$parentDir = dirname($parentDir);
    }
}


sub reverseGetfaclRes {

    my ($faclRes) = @_;

    my @faclSections = reverse map { rem_ws($_); } split /\n{2,}/, $faclRes;

    my $reversed_faclRes = join("\n\n",@faclSections) . "\n\n";

    return($reversed_faclRes);

}

sub Share {

    my $findNotRecurs = " -maxdepth 0";
    if ($recursive) { $findNotRecurs = ""; }
    my $faclRecurs = " -R";
    if (!$recursive) { $faclRecurs = ""; }
    my $recursTxt = " recursively";
    if (!$recursive) { $recursTxt = ""; }

    if (!userProvidedCredentials()) {
	cgi_die_json("Error in Share: write operations are only allowed via a user's credentials (SSH private key or password), please provide.");
    }

    if (empty($dirPath)) { #empty means the root directory of simple_stash, you can't change its eacl
	cgi_die_json("Error in Share: you cannot modify the eACL of the root directory.", { 'path_exists' => JSON::true, 'write_access' => JSON::false });
    }

    $dirPath =~ s/\/+$//;

    my $fullPath = $fsRoot . "/" . $dirPath;

    if ($dirPath =~ m/^\//) {
	cgi_die_json("Error in Share: The path must be a relative path (not absolute), with no leading \/ character. Files are stashed relative to the stash root of $fsRoot");
    }

    my ($dirPathPar, $dirPathLastPart) = parentPath($dirPath);
    if (!defined($dirPathPar)) {
	cgi_die_json("Error in Share: could not extract parent directory from '${dirPath}'");
    }

    my ($pathInfo_full_info, $pathInfo, $pathInfo_fs_user) = pathInfo([$dirPath,$dirPathPar],0);

    if ($pathInfo_full_info->{'paths_info'}{$dirPath}{'doesnt_exist'}) {
       cgi_die_json("Error in Share: path '${dirPath}' does not exist.", { 'path_exists' => JSON::false });
    }

    if (!defined($pathInfo) || !$pathInfo->{'paths_info'}{$dirPathPar}{'permissions'}{'x'}) { #access denied to modify acl
        cgi_die_json("Error in ModifyEacl: access denied to path '${dirPath}'");
    }

    my $allPathsDown;
    if ($recursive) {
	my $errMsg;
	($allPathsDown, $errMsg) = allPathsUnder($dirPath);
	if (!defined($allPathsDown)) {
	    cgi_die_json("Error in Share, couldn't get all paths under '${dirPath}': $errMsg");
	}
	($pathInfo_full_info, $pathInfo, $pathInfo_fs_user) = pathInfo($allPathsDown,0);
    } else {
	$allPathsDown = [$dirPath];
    }

    my @notOwner = grep { my $curPath = $_;
			  defined($pathInfo_full_info->{'paths_info'}{$curPath}) &&
			  ($pathInfo_full_info->{'paths_info'}{$curPath}{'eacl'}{'owner'} ne $current_user); } @$allPathsDown;
    if (@notOwner) {
	cgi_die_json("Error in Share: only the owner can modify a file or directory's permissions and you are not the owner of $dirPath and its sub-content and so cannot modify permissions${recursTxt}.", { 'path_exists' => JSON::true, 'write_access' => JSON::false });
    }

    my $findCmd = 'find \'' . $fullPath . '\' ' . $findNotRecurs . ' -exec sh -c \'getfacl -p "$1" ; chmod u+rwx "$1"\' sh {} \;';
    my $pre_facl_retVal = evalOrDie({"cmd" => $findCmd,
				     "dont_die" => 1,
				     "success_exit" => { 0 => 1 },
				     "parseJsonFlag" => 0,
				     "msgIfErr" => "Error getting current ACLs and temporarily setting to u+rwx for ${dirPath}${recursTxt}"});

    my $pre_faclResTxt = $pre_facl_retVal->{'res'};
    my $pre_faclretErrMsg = $pre_facl_retVal->{'err_msg'};
    my $pre_faclstderr_contents = $pre_facl_retVal->{'stderr'};
    if (!empty($pre_faclstderr_contents)) {
	if ($pre_faclstderr_contents =~ m/No such file or directory/s) {
	    cgi_die_json("Error in Share: path $dirPath does not exist.", { 'path_exists' => JSON::false });
	}
    }

    if (($pre_faclstderr_contents =~ m/Permission denied/s) ||
	($pre_faclstderr_contents =~ m/Operation not permitted/s)) {
	    cgi_die_json("Error in Share: only the owner can modify a file or directory's permissions and you are not the owner of $dirPath and its sub-content and so cannot modify permissions${recursTxt}.",
			 { 'path_exists' => JSON::true, 'write_access' => JSON::false });
    }

    my $fileType = $pathInfo_full_info->{'paths_info'}{$dirPath}{'type'};

    #Give the file system, e.g. irods, user rx access down the tree and also up the tree, so can
    #get the file for the shared-to user on behalf of them
    giveFsUserAccess($dirPath);

    my $updateWebEaclBashScriptTxt = "";
    my @shareUsersArr = map { rem_ws($_); } split /,/,$shareUsers;
    foreach my $file (@$allPathsDown) {
	my $fileFullPath = $fsRoot . "/" . $file;
	my $webAclHash = $pathInfo_full_info->{'paths_info'}{$file}{'webeacl'} || {};
	my $addedNewUserFlag = 0;
	for my $curUser (@shareUsersArr) { if (!$webAclHash->{'u'}{$curUser}{'r'}) { $webAclHash->{'u'}{$curUser}{'r'} = 1; $addedNewUserFlag = 1; } }
	if ($addedNewUserFlag) {
	    my $webeacl = eacl_hash_to_str($webAclHash);
            $fileFullPath =~ s/'/'\\''/g; #handle single quotes so bash won't barf
	    my $setFattrCmd = "setfattr -x user.webeacl '${fileFullPath}';\n";
	    if (!empty($webeacl)) {
		$setFattrCmd = "setfattr -n user.webeacl -v '${webeacl}' '${fileFullPath}';\n",
	    }
	    $updateWebEaclBashScriptTxt .= $setFattrCmd;
	}
    }

    my $retVal3 =
    evalOrDie({"cmd" => "bash",
	       "stdin_data" => $updateWebEaclBashScriptTxt,
	       "parseJsonFlag" => 0,
	       "msgIfErr" => "Error updating web eACL in Share"});

#    $q->param('user_sshkey','...HIDDEN...');
#    sendUsersEmail(['smitha26'], "share operation results", "CGI object:\n<br><pre>" . Dumper($q) . "</pre><br><br>retVals:<br><pre>" . to_json([$retVal,$retVal2,$retVal3],{utf8 => 1, pretty => 1}) . "</pre>\n\n<br><br>updateWebEaclBashScriptTxt:<br><br>\n\n" . $updateWebEaclBashScriptTxt);

    #remove the full rwx permissions for the current, owning user (restore to what was before)
    evalOrDie({"cmd" => "setfacl --restore=-",
	       "stdin_data" => reverseGetfaclRes($pre_faclResTxt),
	       "parseJsonFlag" => 0,
	       "msgIfErr" => "Error restoring eacl for $dirPath to original values in Share"});

    my $shareMsg;
    my $dirPathEscaped = $dirPath;
    $dirPathEscaped =~ s/\'/__SQ__/g;
    $dirPathEscaped = uri_escape($dirPathEscaped);
    my $fsParamTxt = "";
    if (!empty($fs) && ($fs ne 'default')) { $fsParamTxt = "&fs=${fs}"; }
    if ($fileType eq 'D') {
	$shareMsg = <<EOF;
User '${current_user}' has shared directory '${dirPath}' with you, follow this link to view it in the web UI:<p>

<a href='${stashUIFullUrl}?root=${dirPathEscaped}${fsParamTxt}'>${dirPath}</a><p>

You can then use the context menus there to download it as a zip file.
EOF
    } elsif ($fileType eq 'F') {
	$shareMsg = <<EOF;
User '${current_user}' has shared file '${dirPath}' with you, click this link to view/download it:<p>

<a href='${stashUIFullUrl}?root=${dirPathEscaped}&postrd=download_file&disposition=inline${fsParamTxt}'>${dirPath}</a>
EOF
    } else {
	cgi_die_json("Error: unknown file type $dirPath in Share");
    }

    sendUsersEmail(\@shareUsersArr, "${current_user} has shared '${dirPath}' with you", $shareMsg);

    printHeader('application/json');
    my $retObj = { 'success' => JSON::true, 'msg' => "Successfully shared path ${dirPath}${recursTxt}",
		   'path_exists' => JSON::true,
		   'write_access' => JSON::true };

    print to_json($retObj);

}

sub DetermineUserAccess_form {

    printHeader();

    print <<EOF;
<html>
<head><title>DetermineUserAccess</title>
<style>
#deteremineuseraccess {
    font-family: "Trebuchet MS", Arial, Helvetica, sans-serif;
    border-collapse: collapse;
    width: 100%;
}

#deteremineuseraccess td, #deteremineuseraccess th {
    border: 1px solid #ddd;
    padding: 8px;
}

#deteremineuseraccess tr:nth-child(even){background-color: #f2f2f2;}

#deteremineuseraccess tr:hover {background-color: #ddd;}

#deteremineuseraccess th {
    padding-top: 12px;
    padding-bottom: 12px;
    text-align: left;
    background-color: #004851;
    color:  #8D9093;
}

</style>
</head>
<body>
<center><h3>DetermineUserAccess</h3></center>
Determine the filesystem, web, and overall (i.e. combining both filesystem and web eacl) specific rights (read, write, and/or execute) that the currently authenticated user has to a given file or directory. Dir or File Path should be the full relative path to the directory or file. Choose the Filesystem you want to work with (the system can be configured to manage multiple file systems, both local or remote). At least 'x' filesystem access or 'r' web-based access to the parent directory is required (except for the root which anyone can access via this service). Note that if a private SSH key or the user's password is NOT passed, then file system based permissions cannot be determined for the user and will be set to empty (no permissions).
<form method='POST' enctype='multipart/form-data' action='${thisScriptName}'>
<table id="deteremineuseraccess"><tr><th>INPUT</th><th>INPUT VALUE</th></tr>
<tr><td>Dir or File Path:</td><td><input style="width:100%" type=text name=dir_path /></td></tr>
<tr><td>Filesystem:</td><td>${fsSelTxt}</td></tr>
<tr><td>Password:</td><td><input style="width:100%" type=text name=user_password /></td></tr>
<tr><td>SSH Private Key:</td><td><textarea style="width:100%" rows=3 id=user_sshkey name=user_sshkey></textarea></td></tr>
</table><p>
<input type=submit value=Exec />
<input type=hidden name=a value=determine_user_access />
<input type=hidden name=stage value=exec />
</form>
<hr><a href='${thisScriptName}'>home</a>
</body>
</html>
EOF

}

sub DetermineUserAccess_svc {

    if (empty($dirPath)) { #empty means the root directory of simple_stash, normalize to simple empty string
	$dirPath = "";
    } else {
	$dirPath =~ s/\/+$//;
    }

    if ($dirPath =~ m/^\//) {
	cgi_die_json("Error in DetermineUserAccess_svc: The path must be a relative path (not absolute), with no leading \/ character. Files are stashed relative to the stash root of $fsRoot");
    }

    my $canReadFlag = 0;
    my ($pathInfo_full_info, $pathInfo, $pathInfo_fs_user);

    if (empty($dirPath)) { #root
	($pathInfo_full_info, $pathInfo, $pathInfo_fs_user) = pathInfo([$dirPath],0);
	$canReadFlag = 1;
    } else {
	my ($dirPathPar, $dirPathLastPart) = parentPath($dirPath);
	if (!defined($dirPathPar)) {
	    cgi_die_json("Error in DetermineUserAccess_svc: could not extract parent directory from '${dirPath}'");
	}

	($pathInfo_full_info, $pathInfo, $pathInfo_fs_user) = pathInfo([$dirPath,$dirPathPar],0);

	if ($pathInfo_full_info->{'paths_info'}{$dirPath}{'doesnt_exist'}) {
	    cgi_die_json("Error in DetermineUserAccess_svc: path '${dirPath}' does not exist.", { 'path_exists' => JSON::false });
	}

	if (defined($pathInfo) && $pathInfo->{'paths_info'}{$dirPathPar}{'permissions'}{'x'}) { #can view ACL
	    $canReadFlag = 1;
	} else { #check webeacl (i.e. web access rules)
	    my $webPerms = determineWebPerms($pathInfo_full_info->{'paths_info'}{$dirPathPar}{'webeacl'});
	    if ($webPerms->{'r'}) {
		$canReadFlag = 1;
	    }
	}
    }

    if (!$canReadFlag) {
        cgi_die_json("Error in DetermineUserAccess_svc: access denied to path '${dirPath}'");
    }

    my ($userAccess, $userAccess_fs, $userAccess_web) = ({},{},{});
    if (defined($pathInfo)) {
       $userAccess_fs = $pathInfo->{'paths_info'}{$dirPath}{'permissions'};
    }

    my $webPerms = determineWebPerms($pathInfo_full_info->{'paths_info'}{$dirPath}{'webeacl'});
    addPerms($webPerms, $userAccess_web);

    map { $userAccess->{$_} = 1; } (keys %$userAccess_fs, keys %$userAccess_web);

    my $userAccessForJson = {};
    map { $userAccessForJson->{$_} = $userAccess->{$_} ? JSON::true : JSON::false; } keys %$userAccess;
    my $userAccessForJson_fs = {};
    map { $userAccessForJson_fs->{$_} = $userAccess_fs->{$_} ? JSON::true : JSON::false; } keys %$userAccess_fs;
    my $userAccessForJson_web = {};
    map { $userAccessForJson_web->{$_} = $userAccess_web->{$_} ? JSON::true : JSON::false; } keys %$userAccess_web;
    printHeader('application/json');
    my $retObj = { 'success' => JSON::true, 'msg' => "Successfully got access for user $current_user to path $dirPath",
		   'directory_exists' => JSON::true,
		   'user_access' => $userAccessForJson,
                   'user_access_fs' => $userAccessForJson_fs,
                   'user_access_web' => $userAccessForJson_web };

    print to_json($retObj);

}

sub Move_form {

    printHeader();

    print <<EOF;
<html>
<head><title>Move</title>
<style>
#move {
    font-family: "Trebuchet MS", Arial, Helvetica, sans-serif;
    border-collapse: collapse;
    width: 100%;
}

#move td, #move th {
    border: 1px solid #ddd;
    padding: 8px;
}

#move tr:nth-child(even){background-color: #f2f2f2;}

#move tr:hover {background-color: #ddd;}

#move th {
    padding-top: 12px;
    padding-bottom: 12px;
    text-align: left;
    background-color: #004851;
    color:  #8D9093;
}

</style>
</head>
<body>
<center><h3>Move</h3></center>
Move a specified relative file or directory path (relative to the root) to a new path, for example move directory path <i>results/my_project/prod1</i> to <i>results/my_new_project/prod1</i>. This can also be used for simple renaming of files or directories, e.g. move <i>results/output.txt</i> to <i>results/output_final.txt</i>. You must have write access to the specified directory or file path's parent (and write access to the target directory for non-renames) or you will receive an error response. Choose the Filesystem you want to work with (the system can be configured to manage multiple file systems, both local or remote). An SSH private key or the user's password must be provided in order to have file system extended ACL considered (otherwise only web-access extended ACL will be considered) and is required for any write operations like this service.
<form method='POST' enctype='multipart/form-data' action='${thisScriptName}'>
<table id="move"><tr><th>INPUT</th><th>INPUT VALUE</th></tr>
<tr><td>Dir or File Path:</td><td><input style="width:100%" type=text name=dir_path /></td></tr>
<tr><td>New Path:</td><td><input style="width:100%" type=text name=new_path /></td></tr>
<tr><td>Filesystem:</td><td>${fsSelTxt}</td></tr>
<tr><td>Password:</td><td><input style="width:100%" type=text name=user_password /></td></tr>
<tr><td>SSH Private Key:</td><td><textarea style="width:100%" rows=3 id=user_sshkey name=user_sshkey></textarea></td></tr>
</table><p>
<input type=submit value=Exec />
<input type=hidden name=a value=move />
<input type=hidden name=stage value=exec />
</form>
<hr><a href='${thisScriptName}'>home</a>
</body>
</html>
EOF

}

sub Move {

    if (!userProvidedCredentials()) {
	cgi_die_json("Error in Move: write operations are only allowed via a user's credentials (SSH private key or password), please provide.");
    }

    if (empty($dirPath)) { #empty means the root directory of simple_stash, you can't rename it
	cgi_die_json("Error in Move: you cannot move/rename the root directory.", { 'directory_exists' => JSON::true, 'write_access' => JSON::false });
    }

    if (empty($newPath)) {
	cgi_die_json("Error in Move: you must provide a new path (which can't be the root).");
    }


    if ($dirPath =~ m/^\//) {
	cgi_die_json("Error in Move: The path must be a relative path (not absolute), with no leading \/ character. Files are stashed relative to the stash root of $fsRoot");
    }
    if ($newPath =~ m/^\//) {
	cgi_die_json("Error in Move: The new path must be a relative path (not absolute), with no leading \/ character. Files are stashed relative to the stash root of $fsRoot");
    }

    $dirPath =~ s/\/+$//;
    $newPath =~ s/\/+$//;

    my ($dirPathPar, $dirPathLastPart) = parentPath($dirPath);
    if (!defined($dirPathPar)) {
        cgi_die_json("Error in Move: could not parse $dirPath");
    }

    my ($newPathPar, $newPathLastPart) = parentPath($newPath);
    if (!defined($newPathPar)) {
        cgi_die_json("Error in Move: could not parse $newPath");
    }

    #For a move operation, user needs to have at least wx to the parent directory of the dir/file to be moved and wx
    #access to the target directory. In addition, they need at least x access to all higher level directories
    #(for both source and target dirs). A file to be moved does not need any permissions (for either a rename in same dir or move
    #to another dir); a directory to be moved doesn't need any permissions to be renamed, but needs 'w' access for move to another directory
    #In addition, to move a directory to another mounted file system (i.e. not simple rename in same directory or move within
    #same mounted file system), you will need permissions to delete the directory in its original location, so see the comments/notes
    #about permissions in the Delete function for deleting a directory, but basically in addition you'll need the correct permissions
    #to delete any underlying files and dirs of the directory (i.e. 'wx' on the parent dir and 'x' for all higher level dirs). However,
    #it is assumed that a file system managed by Simple Stash and Stash Web UI will be a single mount and so you won't need to do this
    #extra check.

    my ($pathInfo_full_info, $pathInfo, $pathInfo_fs_user) = pathInfo([$dirPath,$dirPathPar],1);

    if ($pathInfo_full_info->{'paths_info'}{$dirPath}{'doesnt_exist'}) {
       cgi_die_json("Error in Move: path '${dirPath}' does not exist.", { 'path_exists' => JSON::false });
    }

    if (!defined($pathInfo) || !($pathInfo->{'paths_info'}{$dirPathPar}{'permissions'}{'w'} &&
	                         $pathInfo->{'paths_info'}{$dirPathPar}{'permissions'}{'x'})) { #access denied to move
        cgi_die_json("Error in Move: access denied to path '${dirPath}'");
    }

    if ($newPathPar ne $dirPathPar) {
	my ($newPathInfo_full_info, $newPathInfo, $newPathInfo_fs_user) = pathInfo([$newPath,$newPathPar],0);
	if (!$newPathInfo_full_info->{'paths_info'}{$newPath}{'doesnt_exist'}) {
	    cgi_die_json("Error in Move: path '${newPath}' already exists.", { 'new_path_exists' => JSON::true });
	}

	if (!defined($newPathInfo) || !($newPathInfo->{'paths_info'}{$newPathPar}{'permissions'}{'w'} &&
				        $newPathInfo->{'paths_info'}{$newPathPar}{'permissions'}{'x'})) { #access denied to move
	    cgi_die_json("Error in Move: access denied to path '${newPath}'");
	}

	if ($pathInfo_full_info->{'paths_info'}{$dirPath}{'type'} eq 'D') {
	    if (!defined($pathInfo) || !$pathInfo->{'paths_info'}{$dirPath}{'permissions'}{'w'}) { #access denied to move
		cgi_die_json("Error in Move: access denied to path '${dirPath}'");
	    }
	}

    } else {
	if (defined($pathInfo_full_info->{'paths_info'}{$dirPathPar}{'files'}{$newPathLastPart})) {
	    cgi_die_json("Error in Move: path '${newPath}' already exists.", { 'new_path_exists' => JSON::true });
	}
    }

    mvPath($dirPath,$newPath);

    printHeader('application/json');
    my $retObj = { 'success' => JSON::true, 'msg' => "Successfully moved path '${dirPath}' to '${newPath}'"  };

    print to_json($retObj);

}


sub DirectoryContents_form {

    printHeader();

    print <<EOF;
<html>
<head><title>DirectoryContents</title>
<style>
#directorycontents {
    font-family: "Trebuchet MS", Arial, Helvetica, sans-serif;
    border-collapse: collapse;
    width: 100%;
}

#directorycontents td, #directorycontents th {
    border: 1px solid #ddd;
    padding: 8px;
}

#directorycontents tr:nth-child(even){background-color: #f2f2f2;}

#directorycontents tr:hover {background-color: #ddd;}

#directorycontents th {
    padding-top: 12px;
    padding-bottom: 12px;
    text-align: left;
    background-color: #004851;
    color:  #8D9093;
}

</style>
</head>
<body>
<center><h3>DirectoryContents</h3></center>
Retrieve the files and sub-directories inside a specified relative directory path (relative to the root), for example <i>results/my_project/prod1</i>. You must have read access to the specified directory path or you will receive an error response. Leave the directory path blank to retrieve the root directory's contents. Choose the Filesystem you want to work with (the system can be configured to manage multiple file systems, both local or remote). An SSH private key or the user's password must be provided in order to have file system extended ACL considered (otherwise only web-access extended ACL will be considered) and is required for any write operations.
<form method='POST' enctype='multipart/form-data' action='${thisScriptName}'>
<table id="directorycontents"><tr><th>INPUT</th><th>INPUT VALUE</th></tr>
<tr><td>Directory Path:</td><td><input style="width:100%" type=text name=dir_path /></td></tr>
<tr><td>Filesystem:</td><td>${fsSelTxt}</td></tr>
<tr><td>Password:</td><td><input style="width:100%" type=text name=user_password /></td></tr>
<tr><td>SSH Private Key:</td><td><textarea style="width:100%" rows=3 id=user_sshkey name=user_sshkey></textarea></td></tr>
</table><p>
<input type=submit value=Exec />
<input type=hidden name=a value=directory_contents />
<input type=hidden name=stage value=exec />
</form>
<hr><a href='${thisScriptName}'>home</a>
</body>
</html>
EOF

}

#See here: https://stackoverflow.com/questions/4665051/check-if-passed-argument-is-file-or-directory-in-bash
sub fileType {

    my ($fullPath) = @_;

    $fullPath =~ s/'/'\\''/g; #handle single quotes so bash won't barf

    my $bashScriptTxt = <<EOF;
if [[ -d '${fullPath}' ]]; then
    echo "directory"
elif [[ -f '${fullPath}' ]]; then
    echo "file"
else
    echo "other"
fi
EOF

    my $retVal = evalOrDie({"cmd" => "bash",
			    "stdin_data" => $bashScriptTxt,
			    "msgIfErr" => "Error checking if ${fullPath} is a directory"});

    my $retRes = rem_ws($retVal->{'res'});

    return($retRes);

}

sub DirectoryContents {

    if (empty($dirPath)) { #empty means the root directory of simple_stash, normalize to simple empty string
	$dirPath = "";
    } else {
	$dirPath =~ s/\/+$//;
    }

    if ($dirPath =~ m/^\//) {
	cgi_die_json("Error in DirectoryContents: The path must be a relative path (not absolute), with no leading \/ character. Files are stashed relative to the stash root of $fsRoot");
    }

    my ($pathInfo_full_info, $pathInfo, $pathInfo_fs_user) = pathInfo([$dirPath],1);

    if ($pathInfo_full_info->{'paths_info'}{$dirPath}{'doesnt_exist'}) {
       cgi_die_json("Error in DirectoryContents: path '${dirPath}' does not exist.", { 'path_exists' => JSON::false });
    }

    my $fileType = $pathInfo_full_info->{'paths_info'}{$dirPath}{'type'};
    if ($fileType ne 'D') {
       cgi_die_json("Error in DirectoryContents: path '${dirPath}' is not a directory.");
    }

    my $canReadFlag = 0;
    if (defined($pathInfo) && $pathInfo->{'paths_info'}{$dirPath}{'permissions'}{'r'}) { #can read using user's account/ssh key
       $canReadFlag = 1;
    } else { #check webeacl (i.e. web access rules)
	my $webPerms = determineWebPerms($pathInfo_full_info->{'paths_info'}{$dirPath}{'webeacl'});
	if ($webPerms->{'r'}) { $canReadFlag = 1; }
    }

    if (!$canReadFlag) {
        cgi_die_json("Error in DirectoryContents: access denied to path '${dirPath}'");
    }

    printHeader('application/json');
    my $retObj = { 'success' => JSON::true, 'msg' => "Successfully got contents of directory $dirPath",
		   'directory_contents' => $pathInfo_full_info->{'paths_info'}{$dirPath}{'files'},
		   'directory_exists' => JSON::true,
		   'read_access' => JSON::true };
    if (defined($pathInfo_full_info->{'paths_info'}{$dirPath}{'files_symlink_targets'})) {
	$retObj->{'files_symlink_targets'} = $pathInfo_full_info->{'paths_info'}{$dirPath}{'files_symlink_targets'};
    }
    print to_json($retObj);

}

sub CreateSymlink_form {

    printHeader();

    print <<EOF;
<html>
<head><title>CreateSymlink</title>
<style>
#createsymlink {
    font-family: "Trebuchet MS", Arial, Helvetica, sans-serif;
    border-collapse: collapse;
    width: 100%;
}

#createsymlink td, #createsymlink th {
    border: 1px solid #ddd;
    padding: 8px;
}

#createsymlink tr:nth-child(even){background-color: #f2f2f2;}

#createsymlink tr:hover {background-color: #ddd;}

#createsymlink th {
    padding-top: 12px;
    padding-bottom: 12px;
    text-align: left;
    background-color: #004851;
    color:  #8D9093;
}

</style>
</head>
<body>
<center><h3>CreateSymlink</h3></center>
Create a new symbolic link <b>Symlink Path</b>(relative to the root directory), i.e. a link to an already existing directory or file <b>Target Path</b>. You must have write access (via filesystem ACL; web-based extended ACL is only considered and used for read operations) to the directory path where the symlink will be created, or you will get an error response. For example, if you specify to create symlink <i>results/my_proj/proj_data_link</i> and <i>results/my_proj</i> exists but you do not have write access to it, then you will receive an error response. If the full path to the directory does not exist it will be created as necessary (i.e. basically a 'mkdir -p PATH' will be done) with each created path segment having base access of the uploading user having 'rwx' access. However, you must have write access to the nearest existing parent directory or you will get an error response. Choose the Filesystem you want to work with (the system can be configured to manage multiple file systems). An SSH private key or the user's password must be provided in order to have file system extended ACL considered (otherwise only web-access extended ACL will be considered) and is required for any write operations like this service.
<form method='POST' enctype='multipart/form-data' action='${thisScriptName}'>
<table id="createsymlink"><tr><th>INPUT</th><th>INPUT VALUE</th></tr>
<tr><td>Symlink Path:</td><td><input style="width:100%" type=text name=dir_path /></td></tr>
<tr><td>Target Path:</td><td><input style="width:100%" type=text name=target_path /></td></tr>
<tr><td>Filesystem:</td><td>${fsSelTxt}</td></tr>
<tr><td>Password:</td><td><input style="width:100%" type=text name=user_password /></td></tr>
<tr><td>SSH Private Key:</td><td><textarea style="width:100%" rows=3 id=user_sshkey name=user_sshkey></textarea></td></tr>
</table><p>
<input type=submit value=Exec />
<input type=hidden name=a value=create_symlink />
<input type=hidden name=stage value=exec />
</form>
<hr><a href='${thisScriptName}'>home</a>
</body>
</html>
EOF

}

sub CreateSymlink {

    if (empty($targetPath)) { #empty means the root directory of simple_stash, normalize to simple empty string
	$targetPath = "";
    } else {
	$targetPath =~ s/\/+$//;
    }

    if (empty($dirPath)) {
       cgi_die_json("Error in CreateSymlink: you must specify the location/name of the symlink.");
    }

    if (!userProvidedCredentials()) {
	cgi_die_json("Error in CreateSymlink: write operations are only allowed via a user's credentials (SSH private key or password), please provide.");
    }

    if (($dirPath =~ m/^\//) || ($targetPath =~ m/^\//)) {
	cgi_die_json("Error in CreateSymlink: paths must be relative paths (not absolute), with no leading \/ character.");
    }

    my ($pathInfo_full_info_target, $pathInfo_target, $pathInfo_fs_user_target) = pathInfo([$targetPath],0);

#    use Data::Dumper;
#    print "Content-Type: text/plain\n\n";
#    print Dumper($pathInfo_full_info_target) . "\n";
#    exit;

    if ($pathInfo_full_info_target->{'paths_info'}{$targetPath}{'doesnt_exist'}) {
       cgi_die_json("Error in CreateSymlink: symlink target '${targetPath}' does not exist.");
    }
    my $userAccess_fs_target = {};
    if (defined($pathInfo_target)) {
	$userAccess_fs_target = $pathInfo_target->{'paths_info'}{$targetPath}{'permissions'};
    }

    if (!$userAccess_fs_target->{'r'}) {
        cgi_die_json("Error in CreateSymlink: access denied to create symlink: you do not have read access to the target '${targetPath}'.");
    }

    my $allSubPaths = genAllSubPaths($dirPath);
    my ($pathInfo_full_info, $pathInfo, $pathInfo_fs_user) = pathInfo($allSubPaths,0);

    my $exists_i; my $curPath; my $curPathInfo; my $lastFlag = 0;
    for ($exists_i = 0; $exists_i < @$allSubPaths; $exists_i++) {
        $curPath = $allSubPaths->[$exists_i];
        $curPathInfo = $pathInfo_full_info->{'paths_info'}{$curPath};
        if (!$curPathInfo->{'doesnt_exist'}) { $lastFlag = 1; last; }
    }

    if (!$lastFlag) {
        cgi_die_json("Error in CreateSymlink: $dirPath nor any of it's parent directories exist");
    }

    if ($exists_i == 0) {
	cgi_die_json("Error in CreateSymlink: path '${dirPath}' already exists.");
    }

    my $userAccess_fs = {};
    if (defined($pathInfo)) {
	$userAccess_fs = $pathInfo->{'paths_info'}{$curPath}{'permissions'};
    }

    if (!($userAccess_fs->{'w'} && $userAccess_fs->{'x'})) {
        cgi_die_json("Error in CreateSymlink: access denied to create symlink: you do not have write/execute access to ${dirPath} parent directories.");
    }

    for (my $i = $exists_i - 1; $i > 0; $i--) {
        $curPath = $allSubPaths->[$i];
        _CreateOneDir($curPath);
    }

#    _CreateOneDir($dirPath);
#
#    #Now just call ModifyEacl
#    $recursive = 0;
#    ModifyEacl(1);

    my $fullPathSymlink = $fsRoot . "/" . $dirPath;
    my $fullPathTarget = $fsRoot . "/" . $targetPath;

    evalOrDie({"cmd" => "ln -s '${fullPathTarget}' '${fullPathSymlink}'","parseJsonFlag" => 0,"msgIfErr" => "Error in CreateSymlink"});

    printHeader('application/json');
    my $retObj = { 'success' => JSON::true, 'msg' => "Successfully created symlink '${dirPath}' with target '${targetPath}'." };
    print to_json($retObj);

}


sub _CreateOneDir {

    my ($dirPath) = @_;

    my $fullPath = $fsRoot . "/" . $dirPath;

    evalOrDie({"cmd" => "mkdir '${fullPath}'","parseJsonFlag" => 0,"msgIfErr" => "Error doing mkdir in _CreateOneDir"});
    evalOrDie({"cmd" => "chmod 0700 '${fullPath}'","parseJsonFlag" => 0,"msgIfErr" => "Error doing chmod in _CreateOneDir"});

}

sub CreateDir {

    if (empty($dirPath)) { #empty means the root directory of simple_stash, normalize to simple empty string
	$dirPath = "";
    } else {
	$dirPath =~ s/\/+$//;
    }

    if (!userProvidedCredentials()) {
	cgi_die_json("Error in CreateDir: write operations are only allowed via a user's credentials (SSH private key or password), please provide.");
    }

    if ($dirPath =~ m/^\//) {
	cgi_die_json("Error in CreateDir: paths must be relative paths (not absolute), with no leading \/ character.");
    }


    my $allSubPaths = genAllSubPaths($dirPath);
    my ($pathInfo_full_info, $pathInfo, $pathInfo_fs_user) = pathInfo($allSubPaths,0);

    my $exists_i; my $curPath; my $curPathInfo; my $lastFlag = 0;
    for ($exists_i = 0; $exists_i < @$allSubPaths; $exists_i++) {
        $curPath = $allSubPaths->[$exists_i];
        $curPathInfo = $pathInfo_full_info->{'paths_info'}{$curPath};
        if (!$curPathInfo->{'doesnt_exist'}) { $lastFlag = 1; last; }
    }

    if (!$lastFlag) {
        cgi_die_json("Error in CreateDir: $dirPath nor any of it's parent directories exist");
    }

    if ($exists_i == 0) {
	cgi_die_json("Error in CreateDir: path '${dirPath}' already exists.");
    }

    my $userAccess_fs = {};
    if (defined($pathInfo)) {
	$userAccess_fs = $pathInfo->{'paths_info'}{$curPath}{'permissions'};
    }

    if (!($userAccess_fs->{'w'} && $userAccess_fs->{'x'})) {
        cgi_die_json("Error in CreateDir: access denied to create directory: you do not have write/execute access to ${dirPath} parent directories.");
    }

    for (my $i = $exists_i - 1; $i > 0; $i--) {
        $curPath = $allSubPaths->[$i];
        _CreateOneDir($curPath);
    }

    _CreateOneDir($dirPath);

    #Now just call ModifyEacl
    $recursive = 0;
    ModifyEacl(1);

    printHeader('application/json');
    my $retObj = { 'success' => JSON::true, 'msg' => "Successfully created directory $dirPath with base ACL '${base}', FS eACL '${eacl}' and web eACL '${webeacl}'" };
    print to_json($retObj);

}

sub DownloadFile_form {

    printHeader();

    print <<EOF;
<html>
<head><title>DownloadFile</title>
<style>
#downloadfile {
    font-family: "Trebuchet MS", Arial, Helvetica, sans-serif;
    border-collapse: collapse;
    width: 100%;
}

#downloadfile td, #downloadfile th {
    border: 1px solid #ddd;
    padding: 8px;
}

#downloadfile tr:nth-child(even){background-color: #f2f2f2;}

#downloadfile tr:hover {background-color: #ddd;}

#downloadfile th {
    padding-top: 12px;
    padding-bottom: 12px;
    text-align: left;
    background-color: #004851;
    color:  #8D9093;
}

</style>
</head>
<body>
<center><h3>DownloadFile</h3></center>
Download a file stored at a given relative path (relative to the root), for example <i>results/my_project/prod1/output.txt</i>. You must have read access to the file or you will receive an error response. An SSH private key or the user's password must be provided in order to have file system extended ACL considered (otherwise only web-access extended ACL will be considered) and is required for any write operations.
<form method='POST' enctype='multipart/form-data' action='${thisScriptName}'>
<table id="downloadfile"><tr><th>INPUT</th><th>INPUT VALUE</th></tr>

<tr><td>Full Relative Path to File to Download:</td><td><input style="width:100%" type=text name=file_path /></td></tr>
<tr><td>Filesystem:</td><td>${fsSelTxt}</td></tr>
<tr><td>Password:</td><td><input style="width:100%" type=text name=user_password /></td></tr>
<tr><td>SSH Private Key:</td><td><textarea style="width:100%" rows=3 id=user_sshkey name=user_sshkey></textarea></td></tr>
</table><p>
<input type=submit value=Exec />
<input type=hidden name=a value=download_file />
<input type=hidden name=stage value=exec />
</form>
<hr><a href='${thisScriptName}'>home</a>
</body>
</html>
EOF

}

sub DownloadFile {

    if (empty($filePath)) {
	cgi_die_json("Error in DownloadFile: you must provide a file path.");
    }

    if ($filePath =~ m/^\//) {
	cgi_die_json("Error in DownloadFile: The path must be a relative path (not absolute), with no leading \/ character. Files are stashed relative to the stash root of $fsRoot");
    }

    $filePath =~ s/\/+$//;

    my $absStashFilePath = $fsRoot . "/" . $filePath;

    my ($pathInfo_full_info, $pathInfo, $pathInfo_fs_user) = pathInfo([$filePath],0);

    if ($pathInfo_full_info->{'paths_info'}{$filePath}{'doesnt_exist'}) {
       cgi_die_json("Error in DownloadFile: path '${filePath}' does not exist.", { 'path_exists' => JSON::false });
    }

    my $fileType = $pathInfo_full_info->{'paths_info'}{$filePath}{'type'};
    if ($fileType ne 'F') {
       cgi_die_json("Error in DownloadFile: path '${filePath}' is not a file.");
    }

    my $canReadFlag = 0; my $access_as_fs_user;
    if (defined($pathInfo) && $pathInfo->{'paths_info'}{$filePath}{'permissions'}{'r'}) { #can read using user's account/ssh key
       $canReadFlag = 1;
       $access_as_fs_user = 0;
    } else { #need to read using file system user's account/key if possible, and check webeacl (i.e. web access rules)
       if (!defined($pathInfo_fs_user)) {
          $pathInfo_fs_user = pathInfo_aux([$filePath], 0, 1);
          if (!defined($pathInfo_fs_user)) { cgi_die_json("Error in DownloadFile: could not get path information for '${filePath}' as fs user."); }
       }
       if (!$pathInfo_fs_user->{'paths_info'}{$filePath}{'permissions'}{'r'}) {
          cgi_die_json("Error in DownloadFile: path '${filePath}' is not accesible to the system, not readable by the user (if SSH key provided) or file system user.");
       }
       $access_as_fs_user = 1;

       my $webPerms = determineWebPerms($pathInfo_full_info->{'paths_info'}{$filePath}{'webeacl'});
       if ($webPerms->{'r'}) { $canReadFlag = 1; }
    }

    if (!$canReadFlag) {
        cgi_die_json("Error in DownloadFile: access denied to path '${filePath}'");
    }

    my $fileName = "stash_download";
    if ($filePath =~ m/([^\/]+)$/) {
	$fileName = $1;
    }

    #If you had to use the file system user to get the files' permissions (i.e. $pathInfo->{'as_fs_user'} is true)
    #Then you also need to use it for the below evalOrDie operations. In addition, you should actually also confirm
    #the the file system user itself has access to read the file and do the below file and cat commands (e.g.
    #maybe users removed the file system user's permissions outside of the simple_stash system) --- this was checked above.

    my $retVal = evalOrDie({"cmd" => "file -b --mime-type '${absStashFilePath}'",
			    "parseJsonFlag" => 0,
			    "as_fs_user" => $access_as_fs_user,
			    "msgIfErr" => "Error doing file command to determine mime-type of file."});

    my $fileMimeType = $retVal->{'res'};

    if (empty($fileMimeType) || ($fileMimeType !~ m/^.+\/.+$/)) {
	$fileMimeType = "application/octet-stream"; #just use generic mime type
    }

    $fileMimeType = rem_ws($fileMimeType);

    #See here: https://stackoverflow.com/questions/6293893/how-do-i-force-files-to-open-in-the-browser-instead-of-downloading-pdf
    if (!empty($disposition)) {
       if (($disposition ne 'attachment') && ($disposition ne 'inline')) { $disposition = 'attachment'; }
    } else {
       $disposition = 'attachment';
    }

    if (!$nocgi) {
	print <<EOS;
Content-Disposition: ${disposition}; filename="${fileName}"
Content-Type: $fileMimeType

EOS

    }

    execOrDie({"cmd" => "cat '${absStashFilePath}'",
	       "as_fs_user" => $access_as_fs_user,
	       "msgIfErr" => "Error returning file contents in DownloadFile"});

}

sub DownloadDir_form {

    printHeader();

    print <<EOF;
<html>
<head><title>DownloadDir</title>
<style>
#downloaddir {
    font-family: "Trebuchet MS", Arial, Helvetica, sans-serif;
    border-collapse: collapse;
    width: 100%;
}

#downloaddir td, #downloaddir th {
    border: 1px solid #ddd;
    padding: 8px;
}

#downloaddir tr:nth-child(even){background-color: #f2f2f2;}

#downloaddir tr:hover {background-color: #ddd;}

#downloaddir th {
    padding-top: 12px;
    padding-bottom: 12px;
    text-align: left;
    background-color: #004851;
    color:  #8D9093;
}

</style>
</head>
<body>
<center><h3>DownloadDir</h3></center>
Download a directory stored at a given relative path (relative to the root) as a zip file, for example <i>results/my_project/prod1/my_dir</i>. You must have read access to the directory (and all its sub-content) or you will receive an error response. An SSH private key or the user's password must be provided in order to have file system extended ACL considered (otherwise only web-access extended ACL will be considered) and is required for any write operations.
<form method='POST' enctype='multipart/form-data' action='${thisScriptName}'>
<table id="downloaddir"><tr><th>INPUT</th><th>INPUT VALUE</th></tr>

<tr><td>Full Relative Path to Directory to Download:</td><td><input style="width:100%" type=text name=dir_path /></td></tr>
<tr><td>Filesystem:</td><td>${fsSelTxt}</td></tr>
<tr><td>Password:</td><td><input style="width:100%" type=text name=user_password /></td></tr>
<tr><td>SSH Private Key:</td><td><textarea style="width:100%" rows=3 id=user_sshkey name=user_sshkey></textarea></td></tr>
</table><p>
<input type=submit value=Exec />
<input type=hidden name=a value=download_dir />
<input type=hidden name=stage value=exec />
</form>
<hr><a href='${thisScriptName}'>home</a>
</body>
</html>
EOF

}

sub DownloadDir {

    if (empty($dirPath)) {
	cgi_die_json("Error: you must provide a directory path, in DownloadDir");
    }

    if ($dirPath =~ m/^\//) {
	cgi_die_json("Error: in DownloadDir, the path must be a relative path (not absolute), with no leading \/ character. Files and directories are stashed and stored relative to the stash root of $fsRoot");
    }

    my $dirToDownload = $dirPath;

    $dirToDownload =~ s/\/+$//;

    my ($hasZipAccessFlag, $zipErrMsg) = checkZipAccess($dirToDownload);

    if (!$hasZipAccessFlag) {
	cgi_die_json("Error in DownloadDir: access denied to download '${dirPath}' as a zip file.", { 'err_msg' => $zipErrMsg });
    }

    my $as_fs_user = $zipErrMsg; #on success, 2d return value tells which user was used to get the pathInfo for the content to download

    $dirToDownload = $fsRoot . "/" . $dirToDownload;

    my ($dirPath, $dirName) = parentPath($dirToDownload);
    if (!defined($dirPath)) {
	cgi_die_json("Error: couldn't parse out dirPath and dirName from $dirToDownload");
    }

#    my $tmpPre = "/scratch/";
#    my $dirName = "akstest";
#    my $zipDir = "${tmpPre}${dirName}";

#    my $cmd = "cd ${tmpPre}; zip -r - ${dirName} > ${dirName}.zip; cat ${zipDir}.zip";
#    my $cmd = "cd ${tmpPre} && zip -r ${dirName}.zip ${dirName} && cat ${dirName}.zip";
#    my $cmd = "cd ${tmpPre}; zip -r - ${dirName} | cat";
#    system("zip -r - ${zipDir}");

#    my $res = `cd ${tmpPre} && zip -r - ${dirName}`;
#    binmode STDOUT;
#    print $res;
#    exit;

    my $cmd = "cd '${dirPath}'; zip -r - '${dirName}' | cat";

    if (!empty($disposition)) {
       if (($disposition ne 'attachment') && ($disposition ne 'inline')) { $disposition = 'attachment'; }
    } else {
       $disposition = 'attachment';
    }

    if (!$nocgi) {
	print <<EOS;
Content-Disposition: ${disposition}; filename="${dirName}.zip"
Content-Type: application/zip

EOS

    }

    execOrDie({"cmd" => $cmd,
	       "as_fs_user" => $as_fs_user,
	       "msgIfErr" => "Error returning dir contents in DownloadDir"});

}

sub StashFile_form {

    printHeader();

    print <<EOF;
<html>
<head><title>StashFile</title>
<style>
#stashfile {
    font-family: "Trebuchet MS", Arial, Helvetica, sans-serif;
    border-collapse: collapse;
    width: 100%;
}

#stashfile td, #stashfile th {
    border: 1px solid #ddd;
    padding: 8px;
}

#stashfile tr:nth-child(even){background-color: #f2f2f2;}

#stashfile tr:hover {background-color: #ddd;}

#stashfile th {
    padding-top: 12px;
    padding-bottom: 12px;
    text-align: left;
    background-color: #004851;
    color:  #8D9093;
}

</style>
</head>
<body>
<center><h3>StashFile</h3></center>
Upload/Stash a file inside a directory path (relative to the root directory) and specify the users and groups who can access the file as base access control (standard Linux user/group/other) and/or extended ACL. Note that 2 versions of extended ACL can be specified, one for web-based access and one for filesystem based access; the web-based extended ACL grants access only through these web services and it is optional. For example upload a file to be stored at path <i>results/my_project/prod1</i> with base access of <i>u:smitha26:rwx,g:xpress:r,o:OTHER:r</i> (which will set the owner to smitha26 and the group to xpress), filesystem extended ACL of <i>g:bioinfo:r,u:russom:rw</i> and web-based extended ACL of <i>u:john:r</i>. You must have write access (via filesystem ACL; web-based ACL is considered and used only for read operations) to the path to stash the uploaded file, or you will get an error response. If the full path to stash the uploaded file does not exist it will be created as necessary (i.e. basically a 'mkdir -p PATH' will be done) with each created path segment having base access of the uploading user having 'rwx' access. However, you must have write access to the nearest existing parent directory or you will get an error response. Note that there is also a special web-access only group called EVERYONE that you can use to specify that any user can access, e.g. EVERYONE:r means any user accessing the system can read the file. Choose the Filesystem you want to work with (the system can be configured to manage multiple file systems). An SSH private key or the user's password must be provided in order to have file system extended ACL considered (otherwise only web-access extended ACL will be considered) and is required for any write operations like this service.
<form method='POST' enctype='multipart/form-data' action='${thisScriptName}'>
<table id="stashfile"><tr><th>INPUT</th><th>INPUT VALUE</th></tr>

<tr><td>File to Stash:</td><td><input type=file name=stash_file /></td></tr>
<tr><td>Path to Stash Uploaded File:</td><td><input style="width:100%" type=text name=dir_path /></td></tr>
<tr><td>Base ACL (File System):</td><td><input style="width:100%" type=text name=base /></td></tr>
<tr><td>Extended ACL (File System):</td><td><input style="width:100%" type=text name=eacl /></td></tr>
<tr><td>Extended ACL (Web Access):</td><td><input style="width:100%" type=text name=webeacl /></td></tr>
<tr><td>Filesystem:</td><td>${fsSelTxt}</td></tr>
<tr><td>Password:</td><td><input style="width:100%" type=text name=user_password /></td></tr>
<tr><td>SSH Private Key:</td><td><textarea style="width:100%" rows=3 id=user_sshkey name=user_sshkey></textarea></td></tr>
</table><p>
<input type=submit value=Exec />
<input type=hidden name=a value=stash_file />
<input type=hidden name=stage value=exec />
</form>
<hr><a href='${thisScriptName}'>home</a>
</body>
</html>
EOF

}

sub StashFile {

    if (empty($dirPath)) { #empty means the root directory of simple_stash, normalize to simple empty string
	$dirPath = "";
    } else {
	$dirPath =~ s/\/+$//;
    }

    if (!userProvidedCredentials()) {
	cgi_die_json("Error in StashFile: write operations are only allowed via a user's credentials (SSH private key or password), please provide.");
    }

    my ($uploadFileName, $tmpFilePath) = read_uploaded_file();

    my $relStashFilePath = $uploadFileName;
    if (!empty($dirPath)) {
       $relStashFilePath = $dirPath . "/" . $uploadFileName;
    }
    my $absStashFilePath = $fsRoot . "/" . $relStashFilePath;

    if ($dirPath =~ m/^\//) {
	cgi_die_json("Error: The path at which to stash a file must be a relative path (not absolute), with no leading \/ character. The file is stashed relative to the stash root of $fsRoot");
    }

    #First see if there is already a file there with the same name
    my ($pathInfo_full_info, $pathInfo, $pathInfo_fs_user) = pathInfo([$relStashFilePath],0);
    if (!$pathInfo_full_info->{'doesnt_exist'}) {
	cgi_die_json("Error in StashFile: '${relStashFilePath}' already exists.");
    }

    my $allSubPaths = genAllSubPaths($dirPath);
    ($pathInfo_full_info, $pathInfo, $pathInfo_fs_user) = pathInfo($allSubPaths,0);

    my $exists_i; my $curPath; my $curPathInfo; my $lastFlag = 0;
    for ($exists_i = 0; $exists_i < @$allSubPaths; $exists_i++) {
        $curPath = $allSubPaths->[$exists_i];
        $curPathInfo = $pathInfo_full_info->{'paths_info'}{$curPath};
        if (!$curPathInfo->{'doesnt_exist'}) { $lastFlag = 1; last; }
    }

    if (!$lastFlag) {
        cgi_die_json("Error in StashFile: $dirPath nor any of it's parent directories exist");
    }

    my $userAccess_fs = {};
    if (defined($pathInfo)) {
	$userAccess_fs = $pathInfo->{'paths_info'}{$curPath}{'permissions'};
    }

    if (!($userAccess_fs->{'w'} && $userAccess_fs->{'x'})) {
        cgi_die_json("Error in StashFile: access denied to stash file: you do not have write/execute access to ${dirPath} or its parent directories.");
    }

    for (my $i = $exists_i - 1; $i >= 0; $i--) {
        $curPath = $allSubPaths->[$i];
        _CreateOneDir($curPath);
    }

#    evalOrDie({"cmd" => "cp $tmpFilePath '$absStashFilePath'","parseJsonFlag" => 0,"msgIfErr" => "Error doing copying of uploaded file"});
    #Change from doing simple cp operation, as this will work both for local mount and via remote ssh
    evalOrDie({"stdin_file" => $tmpFilePath, "cmd" => "cat - > '$absStashFilePath'","parseJsonFlag" => 0,"msgIfErr" => "Error doing copying of uploaded file"});
    evalOrDie({"cmd" => "chmod 0700 '$absStashFilePath'","parseJsonFlag" => 0,"msgIfErr" => "Error doing chmod in StashFile"});

    #Now just call ModifyEacl
    $dirPath = $relStashFilePath;
    $recursive = 0;
    ModifyEacl(1);

    printHeader('application/json');
    my $retObj = { 'success' => JSON::true, 'msg' => "Successfully stashed file at $relStashFilePath" };
    print to_json($retObj);

}

sub genAllSubPaths {

    my ($dirPath) = @_;

    my @allSubPaths;

    my @pathParts = split /\//, $dirPath;

    my $lastIdx = @pathParts - 1;
    for (my $i=$lastIdx; $i>=0; $i--) {
	my $curPath = join("/",@pathParts[0..${i}]);
	push @allSubPaths, $curPath;
    }

    return(\@allSubPaths);

}

#Utility to delete a path (file or dir) from the system
sub delPath {

    my ($path) = @_;

    my $fullPath = $fsRoot . "/" . $path;
    evalOrDie({"cmd" => "rm -fr '$fullPath'",
	       "parseJsonFlag" => 0,
	       "msgIfErr" => "Error doing rm -fr in delPath"});

}

sub mvPath {

    my ($path,$newpath) = @_;

    my $fullPath = $fsRoot . "/" . $path;
    my $newFullPath = $fsRoot . "/" . $newpath;

    evalOrDie({"cmd" => "mv '$fullPath' '$newFullPath'","parseJsonFlag" => 0,"msgIfErr" => "Error moving '${path}' to '${newpath}' by mv operation."});

}

#Just parses for a single file, not a full recursive dump
sub parseGetFattrRes {

    my ($getFattrDumpTxt) = @_;

    my @lines = split /\n/, $getFattrDumpTxt;
    my $attrVals = {};
    my $file;
    for (my $i=0; $i<@lines; $i++) {
	my $curLine = $lines[$i];
	next if (empty($curLine));
	if ($curLine =~ m/^\# file\:\s*(.+)$/) {
	    $file = $1;
	    next;
	}
	if ($curLine =~ m/^([^\=]+)\=\"(.+)\"$/) {
	    my $attr = $1;
	    my $val = $2;
	    $attrVals->{rem_ws($attr)} = rem_ws($val);
	}
    }
    return($attrVals, $file);

}

sub read_uploaded_file {

    if ($nocgi) {
	if (empty($directFilePath)) {
	    cgi_die_json("Error in read_uploaded_file: In CLI mode must pass in direct file system path to file to stash as argument direct_file_path");
	}

	if (empty($stashFileName)) {
	    if ($directFilePath =~ m/([^\/]+)$/) {
		$stashFileName = $1;
	    } else { cgi_die_json("Error in read_uploaded_file: Could not parse filename from $directFilePath"); }
	}

	return($stashFileName, $directFilePath);

    } else {

	if (empty($stashFileName)) { cgi_die_json("Error: you did not provide the file name of the file to stash."); }

	my $filehandle  = $q->upload( 'stash_file' );
	my $tmpFilePath = $q->tmpFileName( $filehandle );

	if (empty($tmpFilePath) || (!(-f $tmpFilePath))) {
	    cgi_die_json("Error: No file upload found, you need to upload a file to stash.");
	}

	return($stashFileName, $tmpFilePath);
    }
}

#my ($base_is_valid, $base_err_msg) = check_base_access($base_hash);
sub check_base_access {

    my ($base_hash) = @_;

    my $u_hash = $base_hash->{'u'} || {};
    my $g_hash = $base_hash->{'g'} || {};
    my $o_hash = $base_hash->{'o'} || {};

    if (scalar keys %$u_hash > 1) { return(0,"Only one user access spec allowed"); }
    if (scalar keys %$g_hash > 1) { return(0,"Only one group access spec allowed"); }
    if (scalar keys %$o_hash > 1) { return(0,"Only one other access spec allowed"); }

    if ((scalar keys %$u_hash == 1) &&
	!defined($u_hash->{$current_user})) { return(0,"User access spec must be for the current user '${current_user}'"); }

    return(1);

}

#my $eacl_hash = eacl_str_to_hash($eacl);
#$eacl_hash->{'u'}{$fsUser} = { 'r' => 1, 'w' => 1, 'x' => 1 };
#$eacl = eacl_hash_to_str($eacl_hash);
sub eacl_str_to_hash {

    my ($eacl, $validate_or_die_flag) = @_;

    if (empty($eacl)) { $eacl = ''; } else { $eacl = rem_ws($eacl); }

    my $eacl_hash = {};
    map { my ($type, $userOrGroupName, $perms) = split /\:/, rem_ws($_);
	  if ($validate_or_die_flag) {
	      if (empty($type)) { cgi_die_json("Error: empty type found in '${eacl}', each ACL must specify 'u', 'g' or 'o'"); }
	      if (empty($userOrGroupName)) { cgi_die_json("Error: empty user or group found in ${eacl}'"); }
	  }
	  my %access_hash = map { $_ => 1; } split //, $perms;
	  $eacl_hash->{$type}{$userOrGroupName} = \%access_hash } split /,/,$eacl;

    return($eacl_hash);

}

sub eacl_hash_to_str {

    my ($eacl_hash, $is_base_flag) = @_;

    if (!defined($eacl_hash)) { $eacl_hash = {}; }

    my @all_eacl;

    while (my ($type, $typeHash) = each %$eacl_hash) {
	while (my ($userOrGroupName, $permsHash) = each %$typeHash) {
	    my $perms_str = join('',sort keys %$permsHash);
	    if ($is_base_flag) { $userOrGroupName = ''; } #For base access specs to be used by setfacl, get rid of user or gruop name, e.g. like u::rwx, g::r, etc.
	    push @all_eacl, $type . ":" . $userOrGroupName . ":" . $perms_str;
	}
    }

    my $eacl = join(",",@all_eacl);

    return($eacl);

}

sub execOrDie {

    my ($args) = @_;

    my $cmd = $args->{'cmd'};
    if ($singleQuoteInPathsFlag) { $cmd = handleSingleQuotesInCmd($cmd); }
    my $msgIfErr = $args->{'msgIfErr'};
    my $stdin_data = $args->{'stdin_data'};
    my $stdin_file = $args->{'stdin_file'};
    my $as_fs_user = $args->{'as_fs_user'}; #execute as $fsUser, even if user has passed their SSH private key

    my $errMsg = "Error doing exec of '${cmd}' in execOrDie";
    if (!empty($msgIfErr)) { $errMsg .= ": " . $msgIfErr; }

    my $remoteSshUser = $fsUser;
    my $remoteSshKeyfile = $fsKeyfile;
    my $remoteSshUserPassword;
    if (!empty($user_sshkey) && !$as_fs_user) {
	my ($user_sshkey_fh, $user_sshkey_filename) = tempfile();
#	my $user_sshkey_decoded = decode_base64($user_sshkey);
	my $user_sshkey_decoded = $user_sshkey;
	$user_sshkey_decoded =~ s/^\s+//s;
	$user_sshkey_decoded =~ s/\s+$//s;
	print $user_sshkey_fh $user_sshkey_decoded . "\n";
	close($user_sshkey_fh);
	$remoteSshUser = $current_user;
	$remoteSshKeyfile = $user_sshkey_filename;
	chmod 0600, $remoteSshKeyfile;
    } elsif (!empty($user_password) && !$as_fs_user) {
	$remoteSshUser = $current_user;
	$remoteSshUserPassword = $user_password;
    }

    my $ssh;

    my $retry_ct = 0;
    while (1) {

	my @sshOpts = ('user' => $remoteSshUser,
		       'master_opts' => [-o => "StrictHostKeyChecking=no",
		                         -o => "UserKnownHostsFile=/dev/null"],
		      );
	if (!empty($remoteSshUserPassword)) { push @sshOpts, ('password' => $remoteSshUserPassword); }
	else { push @sshOpts, ('key_path' => $remoteSshKeyfile); }
	if (!empty($fsPort)) { push @sshOpts, ('port' => $fsPort); }

	eval {
	    $ssh = Net::OpenSSH->new($fsHost,@sshOpts);
	};

	if ($ssh->error || $@) {
	    if ($retry_ct++ < RETRY_SSH_CNT) { sleep(1); next; }
	    cgi_die_json("${msgIfErr}:\nCouldn't establish SSH connection to ${remoteSshUser}\@${fsHost}.");
	} else { last; }
    }

    #Note: to get it to work, I had to create directory /usr/share/httpd/.libnet-openssh-perl with these perms:
    #drwx------    2 apache apache     6 May  9 02:07 .libnet-openssh-perl
    #See ctl_dir option for Net::OpenSSH
    my $cmdOpts = {};
    if (!empty($stdin_data)) {
	$cmdOpts->{'stdin_data'} = $stdin_data;
    } elsif (!empty($stdin_file)) {
	$cmdOpts->{'stdin_data'} = slurp_file($stdin_file);
    }

    $cmdOpts->{'stdout_fh'} = *STDOUT;
    $cmdOpts->{'stderr_fh'} = *STDERR;

    $ssh->system($cmdOpts, $cmd)
	or cgi_die_json($errMsg);

    exit;
}

#This won't handle all the cases (e.g. getfacl '/path/to/fred' s cool file.txt'),
#but will handle most common ones (e.g. getfacl '/path/to/fred's cool file.txt'),
sub handleSingleQuotesInCmd {

    my ($cmd) = @_;

    my $cmdToMatch = " " . $cmd . " ";
    my @matches;
    while ($cmdToMatch =~ m/((?<= \').+?(?=\'( |;)))/gs) {
       push @matches, $1;
    }
    foreach my $curMatch (@matches) {
       if ($curMatch =~ m/\'/) {
	  my $curMatch_fixed = $curMatch;
	  #See here about this handling of single quotes: https://stackoverflow.com/questions/1250079/how-to-escape-single-quotes-within-single-quoted-strings
          $curMatch_fixed =~ s/'/'\\''/g;
          $cmd =~ s/$curMatch/$curMatch_fixed/;
       }
    }

    return($cmd);

}

sub evalOrDie {

    my ($args) = @_;

    my $retVal = {};

    my $cmd = $args->{'cmd'};
    if ($singleQuoteInPathsFlag) { $cmd = handleSingleQuotesInCmd($cmd); }
    my $successExit = $args->{'success_exit'};
    my $dontDie = $args->{'dont_die'}; #if don't actually want to die on failure, if true the result and error message will be returned on failure
    my $parseJsonFlag = $args->{'parseJsonFlag'};
    my $msgIfErr = $args->{'msgIfErr'};
    my $stdin_data = $args->{'stdin_data'};
    my $stdin_file = $args->{'stdin_file'};
    my $as_fs_user = $args->{'as_fs_user'}; #execute as $fsUser, even if user has passed their SSH private key

    if (!defined($successExit)) {
	my $exitSucc = EX_SUCC;
	my $exitWarn = EX_WARN;
	$successExit = { $exitSucc => 1, $exitWarn => 1 };
    }

    if (!defined($msgIfErr)) { $msgIfErr = "Error"; }

    my $remoteSshUser = $fsUser;
    my $remoteSshKeyfile = $fsKeyfile;
    my $remoteSshUserPassword;
    if (!empty($user_sshkey) && !$as_fs_user) {
	my ($user_sshkey_fh, $user_sshkey_filename) = tempfile();
#	my $user_sshkey_decoded = decode_base64($user_sshkey);
	my $user_sshkey_decoded = $user_sshkey;
	$user_sshkey_decoded =~ s/^\s+//s;
	$user_sshkey_decoded =~ s/\s+$//s;
	print $user_sshkey_fh $user_sshkey_decoded . "\n";
	close($user_sshkey_fh);
	$remoteSshUser = $current_user;
	$remoteSshKeyfile = $user_sshkey_filename;
	chmod 0600, $remoteSshKeyfile;
    } elsif (!empty($user_password) && !$as_fs_user) {
	$remoteSshUser = $current_user;
	$remoteSshUserPassword = $user_password;
    }

    my $ssh;

    my $retry_ct = 0;
    while (1) {

	my @sshOpts = ('user' => $remoteSshUser,
		       'master_opts' => [-o => "StrictHostKeyChecking=no",
		                         -o => "UserKnownHostsFile=/dev/null"],
		      );
	if (!empty($remoteSshUserPassword)) { push @sshOpts, ('password' => $remoteSshUserPassword); }
	else { push @sshOpts, ('key_path' => $remoteSshKeyfile); }
	if (!empty($fsPort)) { push @sshOpts, ('port' => $fsPort); }

	eval {
	    $ssh = Net::OpenSSH->new($fsHost,@sshOpts);
	};

	if ($ssh->error || $@) {
	    if ($retry_ct++ < RETRY_SSH_CNT) { sleep(1); next; }
	    $retVal->{'err_msg'} = '';
	    if (!empty($ssh->error)) {
		$retVal->{'err_msg'} .= $ssh->error . "\n\n";
	    }
	    if (!empty($@)) {
		$retVal->{'err_msg'} .= $@;
	    }
	    if (!$dontDie) {
		cgi_die_json("${msgIfErr}:\nCouldn't establish SSH connection to ${remoteSshUser}\@${fsHost}.", $retVal);
	    } else {
		return($retVal);
	    }
	} else { last; }
    }

    #Note: to get it to work, I had to create directory /usr/share/httpd/.libnet-openssh-perl with these perms:
    #drwx------    2 apache apache     6 May  9 02:07 .libnet-openssh-perl
    #See ctl_dir option for Net::OpenSSH
    my $cmdOpts = {};
    if (!empty($stdin_data)) {
	$cmdOpts->{'stdin_data'} = $stdin_data;
    } elsif (!empty($stdin_file)) {
	$cmdOpts->{'stdin_data'} = slurp_file($stdin_file);
    }

    my ($out, $err) = $ssh->capture2($cmdOpts, $cmd);

    $retVal->{'res'} = $out;
    $retVal->{'stderr'} = $err;

    if ($ssh->error) {
	$retVal->{'err_msg'} = $ssh->error;
	if (!$dontDie) {
	    cgi_die_json($msgIfErr . "\n\n" . $err, $retVal);
	}
    }

    if ($parseJsonFlag) {
	$retVal->{'res'} = from_json($retVal->{'res'});
    }

    $retVal->{'executed_cmd'} = $cmd;
    $retVal->{'cmd_opts'} = $cmdOpts;

    return($retVal);

}

sub sendUsersEmail {

    my ($usersArr, $subj, $msg) = @_;

    my @allEmails;
    foreach my $curUser (@$usersArr) {
	my ($succ,$current_user_ldap_info) = getUserLdapInfo($curUser);
	my ($current_user_email, $current_user_cn);
	if ($succ) {
	    $current_user_email = $current_user_ldap_info->get_value('mail');
	    $current_user_cn = $current_user_ldap_info->get_value('cn');
	    push @allEmails, $current_user_email;
	}
    }

    my ($succ,$current_user_ldap_info) = getUserLdapInfo($current_user);
    my ($current_user_email, $current_user_cn);
    if ($succ) {
	$current_user_email = $current_user_ldap_info->get_value('mail');
	$current_user_cn = $current_user_ldap_info->get_value('cn');
    }

    sendMail($current_user_email, join(",",@allEmails), $current_user_email, $subj, $msg);

}

sub cgi_die {

    my ($msg) = @_;

    printHeader('text/plain');
    print "$msg\n";
    exit 1;
}

sub cgi_die_json {

    my ($msg, $respAddVals) = @_;

    if (empty($user_sshkey) && empty($user_password)) {
	$msg = $msg . "\n" . "Note that full access requires your password or SSH private key, which you have not provided.";
    }

    my $errorObj = { 'success' => JSON::false, 'msg' => $msg };

    if (defined($respAddVals)) {
	while (my ($k,$v) = each %$respAddVals) {
	    $errorObj->{$k} = $v;
	}
    }

    if ($Config::DEBUG) { #send error email to admin user
	my $errParamsHash = {};
	setParams($errParamsHash);
	$errorObj->{'params'} = $errParamsHash;
	my $jsonErrDumpTxt = to_json($errorObj);
	sendMail(undef, $Config::primary_admin_email, undef, "${thisScriptName} error for user ${current_user}", $jsonErrDumpTxt);
    }

    printHeader('application/json');
    print to_json($errorObj);
    exit 1;
}

sub getFsGroupsAndUsers {

    if (!defined($fs_users)) {
	$fs_users = getFsUsers();
    }
    if (!defined($fs_groups)) {
	$fs_groups = getFsGroups();
    }

    return($fs_users, $fs_groups);

}


sub getFsGroups {

    if (defined($fs_groups)) {
	return($fs_groups);
    }

    my $groups = {};

    my $retVal = evalOrDie({"cmd" => "getent group",
			    "parseJsonFlag" => 0,
			    "msgIfErr" => "Error doing getent group in getFsGroupsAndUsers"});

    my $getEntGroupRes = $retVal->{'res'};

    #see here for getting all local filesystem groups:
    #https://stackoverflow.com/questions/14059916/is-there-a-command-to-list-all-unix-group-names
    map { my @groupParts = split /\:/,rem_ws($_);
	  my $groupName = $groupParts[0];
	  my $groupMembers = $groupParts[3];
	  my $groupMembersHash = {};
	  if (!empty($groupMembers)) {
	      map { $groupMembersHash->{$_} = 1; } split /,/,$groupMembers;
	  }
	  $groups->{$groupName} = $groupMembersHash; } split /\n/, $getEntGroupRes;

    $fs_groups = $groups;

    return($fs_groups);

}

sub getFsUsers {

    if (defined($fs_users)) {
	return($fs_users);
    }

    my $users = {};

    my $retVal = evalOrDie({"cmd" => "getent passwd | cut -d: -f1",
			    "parseJsonFlag" => 0,
			    "msgIfErr" => "Error doing getent passwd in getFsGroupsAndUsers"});

    my $getEntPasswdRes = $retVal->{'res'};

    #Can use getent to get all local users:
    #https://askubuntu.com/questions/410244/a-command-to-list-all-users-and-how-to-add-delete-modify-users
    map { $users->{rem_ws($_)} = 1; } split /\n/, $getEntPasswdRes;

    $fs_users = $users;

    return($fs_users);

}

sub addPerms {

    my ($addPerms, $toPerms) = @_;

    return if (!defined($addPerms));

    map { $toPerms->{$_} = 1; } keys %$addPerms;
}

sub getUserGroups {

    my ($username) = @_;

    my $userFsGroups;
    if (!empty($username)) {

	my $getGroupsCmd = "id -nG ${username}";
	
	my $retVal = evalOrDie({"cmd" => $getGroupsCmd,
				"parseJsonFlag" => 0,
				"msgIfErr" => "Error getting user groups for ${username} in getUserGroups."});

	my $idResTxt = $retVal->{'res'};

	if (!empty($idResTxt)) {
	    $userFsGroups = {};
	    map { $userFsGroups->{rem_ws($_)} = 1; } split /\s+/,$idResTxt;
	}

    }

    return($userFsGroups);

}

sub determineWebPerms {

    my ($webAclHash) = @_;

#my $allUsersWebAccessGroup = "EVERYONE"; #special web-access only group that signifies all users
#my $Config::web_groups = { 'BLAHGROUP' => { 'smitha26' => 1, 'russom' => 1 },
#                   'COOLGROUP' => { 'smitha26' => 1, 'russom' => 1, 'tilfordc' => 1, 'riosca' => 1, 'limje' => 1 } };

    my $userAccess_web = {};

    if (defined($webAclHash)) {
	if (defined($webAclHash->{'u'}{$current_user})) {
	    addPerms($webAclHash->{'u'}{$current_user},$userAccess_web);
	} else {
	    my $group_access_subhash = $webAclHash->{'g'} || {};
	    while (my ($groupName, $groupAccess) = each %$group_access_subhash) {
		my $groupMembersHash = $Config::web_groups->{$groupName};
		if (($groupName eq $allUsersWebAccessGroup) || ($groupMembersHash && $groupMembersHash->{$current_user})) {
		    addPerms($groupAccess, $userAccess_web);
		}
	    }
	}
    }

    return($userAccess_web);

}


#Returns 1 if the user has access, 0 and error message if not
sub checkZipAccess {

    my ($dirPath) = @_;

    if (empty($dirPath)) { #empty means the root directory of simple_stash, you can't download it
	return (0,"Error in checkZipAccess: you cannot download the root directory.", { 'path_exists' => JSON::true });
    }

    if ($dirPath =~ m/^\//) {
	return(0,"Error in checkZipAccess: The path must be a relative path (not absolute), with no leading \/ character. Files are stashed relative to the stash root of $fsRoot");
    }


    $dirPath =~ s/\/+$//;

    my $fullPath = $fsRoot . "/" . $dirPath;

    my ($pathInfo_full_info, $pathInfo, $pathInfo_fs_user) = pathInfo([$dirPath],0);

    if ($pathInfo_full_info->{'paths_info'}{$dirPath}{'doesnt_exist'}) {
       return (0,"Error in checkZipAccess: path '${dirPath}' does not exist.", { 'path_exists' => JSON::false });
    }

    my $webPerms = determineWebPerms($pathInfo_full_info->{'paths_info'}{$dirPath}{'webeacl'});

    if (!(defined($pathInfo) && $pathInfo->{'paths_info'}{$dirPath}{'permissions'}{'r'} &&
	  $pathInfo->{'paths_info'}{$dirPath}{'permissions'}{'x'}) &&
	  !$webPerms->{'r'}) { #access denied to read the dir
        return (0,"Error in checkZipAccess: access denied to path '${dirPath}'");
    }

    my $as_fs_user;
    if ($pathInfo_full_info->{'paths_info'}{$dirPath}{'type'} eq 'D') { #need to make sure you have access to lower level content

	my ($allPathsDown, $errMsg) = allPathsUnder($dirPath);
	if (!defined($allPathsDown)) {
	    return (0,"Error in DownloadDir: couldn't get all paths under '${dirPath}': $errMsg");
	}

	my @pathInfoResArr = pathInfo($allPathsDown,0);
	my ($pathInfo_full_info, $pathInfo, $pathInfo_fs_user) = @pathInfoResArr;

	my ($hasPerm_fs, $permDownErrMsg_fs) = checkAccessUnder($dirPath,\@pathInfoResArr,{ 'BOTH' => { 'fs' => ['r'] } },{ 'fs' => ['r','x'] });
	my ($hasPerm_web, $permDownErrMsg_web) = checkAccessUnder($dirPath,\@pathInfoResArr,{ 'BOTH' => { 'web' => ['r'] } },{ 'web' => ['r'] });
	if (!$hasPerm_fs && !$hasPerm_web) { return (0,"Error in checkZipAccess: you do not have access to download '${dirPath}' as a zip file"); }
	$as_fs_user = $pathInfo_full_info->{'as_fs_user'};
    }

    #Check if too big to download as zip file
    my ($retVal,$errMsg) = checkDirSize($dirPath);
    if (!$retVal) {
	return(0,$errMsg);
    }

    return (1,$as_fs_user);

}

sub checkDirSize {

    my ($dirPath,$as_fs_user) = @_;

    $as_fs_user = $as_fs_user ? 1 : 0;

    my $fullPath = $fsRoot . "/" . $dirPath;

    #Check if too big to download as zip file
    my $retVal_du = evalOrDie({"cmd" => "du -sk '$fullPath'",
			       "parseJsonFlag" => 0,
			       "as_fs_user" => $as_fs_user,
			       "dont_die" => 1,
			       "msgIfErr" => "Error checking size of zip download $dirPath"});

    my $stderr = $retVal_du->{'stderr'};

    if ($stderr !~ m/Permission denied/) {
	my $du_res = $retVal_du->{'res'};
	if ($du_res =~ m/^\s*(\d+)/) {
	    my $sizeInKilobytes = $1;
	    if ($sizeInKilobytes > (1024 * 500)) {
		return (0,"Error: Maximum zip download size is 500 MB");
	    }
	}
	return 1;
    } elsif (!userProvidedCredentials() || $as_fs_user) {
	return(0,"Error: could not check directory size of '${dirPath}', permission denied.");
    } elsif (!$as_fs_user) {
	my ($rv,$em) = checkDirSize($dirPath,1);
	return($rv,$em);
    }

}


#Assumes you have already checked 'x' access for all higher level dirs to dirPath
#my ($permDownFlag, $permDownErrMsg) = checkDirDelAccessDown($dirPath, $current_user, $thePathInfo->{'user_fs_groups'});
sub checkDirDelAccessDown {

    my ($dirPath, $user, $userFsGroups) = @_;

    if (empty($user)) { $user = $current_user; }
    if (empty($dirPath)) { cgi_die_json("Error in checkDirDelAccessDown: you must provide a value for dirPath."); }

    if (!defined($userFsGroups)) {
	$userFsGroups = getUserGroups($user);
    }

    my $fullPath = $fsRoot . "/" . $dirPath;

    my $faclResByFile = {};

    my $retVal = evalOrDie({"cmd" => "getfacl -R -p '$fullPath'",
			    "dont_die" => 1,
			    "parseJsonFlag" => 0});

    my ($faclResTxt,$errMsg, $stderrResTxt) = ($retVal->{'res'},$retVal->{'err_msg'},$retVal->{'stderr'});

    if (!empty($stderrResTxt)) {
	my $permissionDeniedRes = join("\n", grep { m/Permission denied/; } split /\n/, $stderrResTxt);
	if (!empty($permissionDeniedRes)) {
	    my $errRetMsg = "Error in checkDirDelAccessDown getting recursive FS system eacl for $dirPath";
	    if ($Config::DEBUG) {
		$errRetMsg .= ":\n${permissionDeniedRes}";
	    } else {
		$errRetMsg .= ": permission denied";
	    }
	    return(0,$errRetMsg);
	}
    }

    map { my $curFileFaclRes = parseGetfaclRes(rem_ws($_));
	  $faclResByFile->{$curFileFaclRes->{'file'}} = $curFileFaclRes; } split/\n+\s*\n+/, $faclResTxt;

    foreach my $curFile (keys %$faclResByFile) {

	my $parentDir = dirname($curFile);
	if (defined($faclResByFile->{$parentDir})) {
	    my ($userAccess_par, $userAccess_fs_par, $userAccess_web_par) = determineUserAccess($user, $userFsGroups,
												$faclResByFile->{$parentDir}, {});
	    if (!($userAccess_fs_par->{'w'} && $userAccess_fs_par->{'x'})) {
		return(0,"Error: You do not have 'wx' access to '${parentDir}' which is required to delete or move '${curFile}'.");
	    }

	    while (1) {
		last if ($parentDir eq "/"); #went up to root
		my $parentDir = dirname($parentDir);
		if (defined($faclResByFile->{$parentDir})) {
		    my ($userAccess_par, $userAccess_fs_par, $userAccess_web_par) = determineUserAccess($user, $userFsGroups,
													$faclResByFile->{$parentDir}, {});
		    if (!$userAccess_fs_par->{'x'}) {
			return(0,"Error: You do not have 'x' access to '${parentDir}' which is required to delete or move '${curFile}'.");
		    }
		} else { last; }
	    }
	}
    }

    return(1);

}

#returns the paths as absolute paths (with fsRoot included in the path)
sub allPathsUnder {

    my ($dirPath, $as_fs_user) = @_;

    $as_fs_user = $as_fs_user ? 1 : 0;

    my $fullPath = $fsRoot . "/" . $dirPath;

    my $retVal = evalOrDie({"cmd" => "find '$fullPath'",
			    "dont_die" => 1,
			    "as_fs_user" => $as_fs_user,
			    "parseJsonFlag" => 0});

    my $res = $retVal->{'res'};
    my $stderr = $retVal->{'stderr'};

    my $errMsg;
    my @stderr_lines = split /\n/,$stderr;
    foreach my $curStderrLine (@stderr_lines) {
	if ($curStderrLine =~ m/^find\:\s+\‘${fsRoot}\/(.+)\’\:\s+Permission denied/) {
	    my $deniedPath = $1;
	    $errMsg = "Error in allPathsUnder: access denied to path '${deniedPath}'";
	    last;
	} elsif ($curStderrLine =~ m/find\:\s+\‘${fsRoot}\/(.+)\’\:\s+No such file or directory/) {
	    my $notExistsPath = $1;
	    $errMsg = "Error in allPathsUnder: path '${notExistsPath}' does not exist.";
	    last;
	}
    }

    if (empty($errMsg)) {
	my @underPaths = map {
	    my $p = rem_ws($_);
	    if ($p =~ m/^${fsRoot}\/(.+)$/) { $p = $1; } else { cgi_die_json("Error in allPathsUnder: bad path not in '${fsRoot}': '${$p}'"); }
	    $p;
	} split /\n/, $res;
	return(\@underPaths);
    } elsif (!userProvidedCredentials() || $as_fs_user) { #used file system user account and it was inaccessible
	return(undef,$errMsg);
    } elsif (!$as_fs_user) { #used user's SSH private key, so now try with file system user
	my ($ap,$em) =  allPathsUnder($dirPath,1);
	return($ap,$em);
    }

}

sub parentPath {

    my ($dirPath) = @_;

    if ($dirPath =~ m/^(.+)\/([^\/]+)$/) {
        my $dirPathPar = $1; my $dirPathLastPart = $2;
	return($dirPathPar, $dirPathLastPart);
    } elsif ($dirPath =~ m/^([^\/]+)$/) { #file or dir at root
        my $dirPathPar = ''; my $dirPathLastPart = $1;
	return($dirPathPar, $dirPathLastPart);
    } else {
	return;
    }
}

#$pathReqPerms are permissions required of each file or dir below $dirPath.
#$parReqPerms are permissions required of the parent dir of each file or dir below $dirPath.
#Doesn't check the parent of $dirPath (assumes that will be done by the caller)
sub checkAccessUnder {

    my ($dirPath, $pathInfoResArr, $pathReqPerms, $parReqPerms) = @_;

    if (empty($dirPath)) { cgi_die_json("Error in checkAccessUnder: you must provide a value for dirPath."); }

    my ($pathInfo_full_info, $pathInfo, $pathInfo_fs_user) = @$pathInfoResArr;

    foreach my $curPath (keys %{ $pathInfo_full_info->{'paths_info'} }) {
	my $curPathInfo_full_info = $pathInfo_full_info->{'paths_info'}{$curPath};
	my ($parPath, $dirFileName) = parentPath($curPath);
	if (!defined($parPath)) { cgi_die_json("Error in checkAccessUnder: could not get parent dir for '${curPath}'"); }
	my $parPathInfo_full_info = $pathInfo_full_info->{'paths_info'}{$parPath};
	my $curPathInfo_user; my $parPathInfo_user;
	if (defined($pathInfo)) {
	    $curPathInfo_user = $pathInfo->{'paths_info'}{$curPath};
	    $parPathInfo_user = $pathInfo->{'paths_info'}{$parPath};
	}

	my $webEacl = $curPathInfo_full_info->{'webeacl'};
	my $webPerms;
	if (defined($webEacl)) {
	    $webPerms = determineWebPerms($webEacl);
	}
	my $webPerms_par;
	if (defined($parPathInfo_full_info)) {
	    my $webEacl_par = $parPathInfo_full_info->{'webeacl'};
	    if (defined($webEacl_par)) {
		$webPerms_par = determineWebPerms($webEacl_par);
	    }
	}

	if (defined($pathReqPerms)) {
	    my $pathTypeReqPerms;
	    if ($curPathInfo_full_info->{'type'} eq 'D') {
		$pathTypeReqPerms = $pathReqPerms->{'D'} || $pathReqPerms->{'BOTH'}
	    } elsif ($curPathInfo_full_info->{'type'} eq 'F') {
		$pathTypeReqPerms = $pathReqPerms->{'F'} || $pathReqPerms->{'BOTH'}
	    }
	    next unless defined($pathTypeReqPerms);
	    while (my ($curPermType, $curTypePermsArr) = each %$pathTypeReqPerms) {
		foreach my $curPerm (@$curTypePermsArr) {
		    if ($curPermType eq 'fs') {
			if (!defined($curPathInfo_user) || !$curPathInfo_user->{'permissions'}{$curPerm}) {
			    return(0,"'${curPerm}' file system access to '${curPath}' is required");
			}
		    } elsif ($curPermType eq 'web') {
			if (!defined($webPerms) || !$webPerms->{$curPerm}) {
			    return(0,"'${curPerm}' web access to '${curPath}' is required");
			}
		    }
		}
	    }
	}
	if (defined($parPathInfo_full_info) && defined($parReqPerms)) {
	    while (my ($curPermType, $curTypePermsArr) = each %$parReqPerms) { #parent can only be dir
		foreach my $curPerm (@$curTypePermsArr) {
		    if ($curPermType eq 'fs') {
			if (!defined($parPathInfo_user) || !$parPathInfo_user->{'permissions'}{$curPerm}) {
			    return(0,"'${curPerm}' file system access to '${parPath}' is required");
			}
		    } elsif ($curPermType eq 'web') {
			if (!defined($webPerms_par) || !$webPerms_par->{$curPerm}) {
			    return(0,"'${curPerm}' web access to '${parPath}' is required");
			}
		    }
		}
	    }
	}
    }

    return(1);

}

sub pathInfo {

    my ($stashPaths, $doLsFlag) = @_;

    my $pathInfo_user; my $pathInfo_fs_user;
    my $pathInfo_full_info; #this will be either the user or file system user pathInfo object, whichever one didn't suffer any lack of permissions

    if (userProvidedCredentials()) { #get using user's credentials
	$pathInfo_user = pathInfo_aux($stashPaths, $doLsFlag, 0);
	if (!defined($pathInfo_user)) { cgi_die_json("Error in pathInfo: could not get path information as user."); }
	if ($pathInfo_user->{'getfattr_permission_denied'} ||
	    $pathInfo_user->{'getfacl_permission_denied'} ||
	    $pathInfo_user->{'stat_permission_denied'} ||
	    $pathInfo_user->{'ls_permission_denied'}) { #also get it as the file system user
	    $pathInfo_fs_user = pathInfo_aux($stashPaths, $doLsFlag, 1);
	    if (!defined($pathInfo_fs_user)) { cgi_die_json("Error in pathInfo: could not get path information as file system user."); }
	    if ($pathInfo_fs_user->{'getfattr_permission_denied'} ||
		$pathInfo_fs_user->{'getfacl_permission_denied'} ||
		$pathInfo_fs_user->{'stat_permission_denied'} ||
		$pathInfo_fs_user->{'ls_permission_denied'}) { #can't get complete info neither as the user or file system user, inaccessible
		cgi_die_json("Error in pathInfo: one or more paths is not accesible to the system, getfattr, stat, and/or ls failed.");
	    } else {
		$pathInfo_full_info = $pathInfo_fs_user;
	    }
	} else {
	    $pathInfo_full_info = $pathInfo_user;
	}
    } else { #no user SSH key, so need to get as file system user
	$pathInfo_fs_user = pathInfo_aux($stashPaths, $doLsFlag, 1);
	if (!defined($pathInfo_fs_user)) { cgi_die_json("Error in pathInfo: could not get path information as file system user."); }
	if ($pathInfo_fs_user->{'getfattr_permission_denied'} ||
	    $pathInfo_fs_user->{'getfacl_permission_denied'} ||
	    $pathInfo_fs_user->{'stat_permission_denied'} ||
	    $pathInfo_fs_user->{'ls_permission_denied'}) { #can't get complete info neither as the user or file system user, inaccessible
	    cgi_die_json("Error in pathInfo: one or more paths is not accesible to the system, getfattr, stat, and/or ls failed.");
	} else {
	    $pathInfo_full_info = $pathInfo_fs_user;
	}
    }

    return($pathInfo_full_info, $pathInfo_user, $pathInfo_fs_user);

}

sub pathInfo_aux {

    my ($stashPaths, $doLsFlag, $as_fs_user) = @_;

    $as_fs_user = $as_fs_user ? 1 : 0;

    my $bashScriptTxt = "";
    for (my $i=0; $i<@$stashPaths; $i++) {

	my $stashPath = $stashPaths->[$i];

	$stashPath =~ s/\/$//;

	my $fullPath = $fsRoot . "/" . $stashPath;
	$fullPath =~ s/'/'\\''/g; #handle single quotes so bash won't barf

	if (empty($stashPath)) { $stashPath = 'ROOT'; } #root

	my $curBashSection = <<EOF;
if [[ -r '${fullPath}' ]]; then
    echo "permissions ${stashPath}: r"
fi
if [[ -x '${fullPath}' ]]; then
    echo "permissions ${stashPath}: x"
fi
if [[ -w '${fullPath}' ]]; then
    echo "permissions ${stashPath}: w"
fi
echo -n "stat ${stashPath}: ";
stat --format="%U,%F" '${fullPath}';
echo "";
echo "GETFATTR ${stashPath}";
getfattr -d --absolute-names '${fullPath}'
echo "END GETFATTR";
echo "GETFACL ${stashPath}";
getfacl -p '${fullPath}';
echo "END GETFACL";
EOF

	if ($doLsFlag) {

	    my $lsCmd = <<EOF;
#note: you can technically exec 'ls' with only -r
#permission on the dir, but it will print errors
#about accessing the files/dirs in it and also,
#importantly, 'ls -QlF' won't give the needed
#info (so can determine which are files and which
#are dirs). In any case, file system user should
#have at least rx permission everywhere and can
#exec 'ls -QlF'
echo "LS RESULT ${stashPath}";
if [ -r '${fullPath}' ] && [ -x '${fullPath}' ]; then
    ls -QlF '${fullPath}';
else
    echo "...___LS_NO_PERMISSION___...";
fi
echo "END LS RESULT";
EOF

            $curBashSection .= $lsCmd;
	}

	$bashScriptTxt .= $curBashSection;

    }

    my $retVal = evalOrDie({"cmd" => "bash",
			    "stdin_data" => $bashScriptTxt,
	                    "parseJsonFlag" => 0,
                            "as_fs_user" => $as_fs_user,
	                    "msgIfErr" => "Error getting file permissions and file information in pathInfo"});

    my $bashRes = $retVal->{'res'};
    my @bashLines = map { rem_ws($_); } split /\n/, $bashRes;

    my $allRetVals = {};

    my $stderr = $retVal->{'stderr'};
    my @stderr_lines = split /\n/,$stderr;
    foreach my $curStderrLine (@stderr_lines) {
       if ($curStderrLine =~ m/getfattr\:\s*${fsRoot}\/(.+)\:\s*No such file or directory/) { #doesn't exist, so permission not relevant
	   my $thePath = $1;
	   $allRetVals->{'paths_info'}{$thePath}{'doesnt_exist'} = 1;
	   $allRetVals->{'doesnt_exist'} = 1;
       } elsif (($curStderrLine =~ m/getfattr\:\s*${fsRoot}\/(.+)\:\s*Permission denied/) ||
		($curStderrLine =~ m/${fsRoot}\/(.+)\:\s+user\.webeacl\:\s+Permission denied/)) { #No permission, so unknown whether exists or not
	   my $thePath = $1;
	   $allRetVals->{'paths_info'}{$thePath}{'getfattr_permission_denied'} = 1;
	   $allRetVals->{'getfattr_permission_denied'} = 1;
       } elsif ($curStderrLine =~ m/stat\:\s+cannot stat\s+\‘${fsRoot}\/(.+)\’\:\s+Permission denied/) { #No permission, so don't know owner or type
	   my $thePath = $1;
	   $allRetVals->{'paths_info'}{$thePath}{'stat_permission_denied'} = 1;
	   $allRetVals->{'stat_permission_denied'} = 1;
       } elsif ($curStderrLine =~ m/getfacl\:\s*${fsRoot}\/(.+)\:\s*No such file or directory$/) { #doesn't exist, so permission not relevant
	   my $thePath = $1;
	   $allRetVals->{'paths_info'}{$thePath}{'doesnt_exist'} = 1;
	   $allRetVals->{'doesnt_exist'} = 1;
       } elsif ($curStderrLine =~ m/getfacl\:\s*${fsRoot}\/(.+)\:\s*Permission denied$/) { #No permission, so unknown whether exists or not
	   my $thePath = $1;
	   $allRetVals->{'paths_info'}{$thePath}{'getfacl_permission_denied'} = 1;
	   $allRetVals->{'getfacl_permission_denied'} = 1;
       }
    }

    my $curSectionTxt = ""; my $inSectionFlag = 0; my $curSectionPath;
    for (my $i=0; $i < @bashLines; $i++) {
       my $curLine = $bashLines[$i];
       if ($curLine =~ m/^(GETFATTR|GETFACL|LS RESULT) (.+)$/) {
          $inSectionFlag = 1;
          $curSectionPath =  $2;
       } elsif ($curLine eq 'END GETFATTR') {
	  my $webAclHash = {};
          if (!empty($curSectionTxt) &&
              !$allRetVals->{'paths_info'}{$curSectionPath}{'doesnt_exist'} &&
              !$allRetVals->{'paths_info'}{$curSectionPath}{'getfattr_permission_denied'}) {
	     my ($attrVals, $file) = parseGetFattrRes($curSectionTxt);
	     my $webAcl = $attrVals->{'user.webeacl'};
	     if (!empty($webAcl)) {
	        $webAclHash = eacl_str_to_hash($webAcl);
	     }
          }
	  $allRetVals->{'paths_info'}{$curSectionPath}{'webeacl'} = $webAclHash;
          $inSectionFlag = 0;
	  $curSectionTxt = "";
       } elsif ($curLine eq 'END GETFACL') {
	  my $getfaclRes = parseGetfaclRes($curSectionTxt);
	  $allRetVals->{'paths_info'}{$curSectionPath}{'eacl'} = $getfaclRes;
          $inSectionFlag = 0;
	  $curSectionTxt = "";
       } elsif ($curLine eq 'END LS RESULT') {
	  my @lsResLines = map { rem_ws($_); } split /\n/,$curSectionTxt;
	  if (rem_ws($lsResLines[0]) eq "...___LS_NO_PERMISSION___...") {
	      if (!$allRetVals->{'paths_info'}{$curSectionPath}{'doesnt_exist'}) {
		  $allRetVals->{'paths_info'}{$curSectionPath}{'ls_permission_denied'} = 1;
		  $allRetVals->{'ls_permission_denied'} = 1;
	      }
	  } else {
              my $files = {};
	      my $files_symlink_targets = {};
	      map { my $curLine = $_;
		    chomp $curLine;
		    if ($curLine =~ m/\"([^\"]+)\" \-\> \"([^\"]+)\"(.?)$/) { #symlink
			my $curEntry = $1;
			my $curEntryTarget = $2;
			my $curEntryType = $3;
			if ($curEntryType eq '/') { $files->{$curEntry} = 'SD'; }
			elsif ($curEntryType eq '*') { $files->{$curEntry} = 'SF'; }
			else { $files->{$curEntry} = 'SF'; }
			if ($curEntryTarget =~ m/^${fsRoot}\/(.+)$/) { $curEntryTarget = $1; }
			$files_symlink_targets->{$curEntry} = $curEntryTarget;
		    } elsif ($curLine =~ m/\"([^\"]+)\"(.?)$/) { #dir or file
			my $curEntry = $1;
			my $curEntryType = $2;
			if ($curEntryType eq '/') { $files->{$curEntry} = 'D'; }
			elsif ($curEntryType eq '*') { $files->{$curEntry} = 'F'; }
			else { $files->{$curEntry} = 'F'; }
		    }
	      } @lsResLines;
              $allRetVals->{'paths_info'}{$curSectionPath}{'files'} = $files;
	      if (scalar keys %$files_symlink_targets) {
		  $allRetVals->{'paths_info'}{$curSectionPath}{'files_symlink_targets'} = $files_symlink_targets;
	      }
          }
          $inSectionFlag = 0;
	  $curSectionTxt = "";
       } elsif ($inSectionFlag) {
          $curSectionTxt .= $curLine . "\n";
       } elsif ($curLine =~ m/^(permissions|stat)\s+(.+?)\:\s*(.+)$/) {
	   my $lineType = $1;
	   my $theStashPath = $2;
	   my $commandRes = $3;
	   if ($lineType eq 'stat') {
	       my @statRes = split /,/, rem_ws($commandRes);
	       
	       $allRetVals->{'paths_info'}{$theStashPath}{'owner'} = $statRes[0];
	       my $type = $statRes[1];
	       if ($statRes[1] eq 'directory') { $type = 'D'; }
	       elsif ($statRes[1] eq 'regular file') { $type = 'F'; }
	       elsif ($statRes[1] eq 'regular empty file') { $type = 'F'; }
	       elsif ($statRes[1] eq 'symbolic link') { $type = 'S'; }
	       $allRetVals->{'paths_info'}{$theStashPath}{'type'} = $type;
	   } else { #permissions
	       $allRetVals->{'paths_info'}{$theStashPath}{$lineType}{$commandRes} = 1;
	   }
       }
    }

    #the input param $as_fs_user is basically a request for which user to do the evalOrDie operation as.
    #However, if the user didn't provide an SSH private key, then the file system user key is used.
    #So the output param as_fs_user tells who's SSH private key was ACTUALLY used, user's or file system user's
    if (!userProvidedCredentials()) { #user didn't provide an SSH private key, so was done as file system user no matter what
	$allRetVals->{'as_fs_user'} = 1;
    } else {
	$allRetVals->{'as_fs_user'} = $as_fs_user;
    }

    my $rootVals = $allRetVals->{'paths_info'}{'ROOT'}; #clean up root key
    if (defined($rootVals)) {
	delete $allRetVals->{'paths_info'}{'ROOT'};
	$allRetVals->{'paths_info'}{''} = $rootVals;
    }

    return($allRetVals);

}

sub determineUserAccess {

    my ($username, $userFsGroups, $getfaclRes, $webAclHash) = @_;

    if (!defined($userFsGroups)) { $userFsGroups = {}; }

    my $userAccess = {}; #combines fs and web
    my $userAccess_fs = {};
    my $userAccess_web = {};

    #See here: https://unix.stackexchange.com/questions/269991/given-the-permissions-owner-and-group-of-a-file-whats-the-algorithm-that-dete
    #And here: https://askubuntu.com/questions/257896/what-is-meant-by-mask-and-effective-in-the-output-from-getfacl
    #And here: https://web.archive.org/web/20161202210810/http://www.vanemery.com/Linux/ACL/POSIX_ACL_on_Linux.html
    #Also here: http://www.informit.com/articles/article.aspx?p=725218&seqNum=5&rll=1
    if (defined($getfaclRes)) {
	my $applyMaskFlag = 0;
	if ($username eq $getfaclRes->{'owner'}) {
	    addPerms($getfaclRes->{'owner_perms'}, $userAccess_fs);
	} elsif (defined($getfaclRes->{'extended_perms'}{'u'}{$username})) {
	    addPerms($getfaclRes->{'extended_perms'}{'u'}{$username}, $userAccess_fs);
	    $applyMaskFlag = 1;
	} elsif ($userFsGroups->{$getfaclRes->{'group'}}) {
	    addPerms($getfaclRes->{'group_perms'}, $userAccess_fs);
	    $applyMaskFlag = 1;
	} else {
	    my $eaclInGroupCt = 0;
	    foreach my $curUserGroup (keys %$userFsGroups) {
		if (defined($getfaclRes->{'extended_perms'}{'g'}{$curUserGroup})) {
		    addPerms($getfaclRes->{'extended_perms'}{'g'}{$curUserGroup}, $userAccess_fs);
		    $eaclInGroupCt++;
		}
	    }

	    if ($eaclInGroupCt <= 0) { #if nothing else matched, just apply 'other' perms
		addPerms($getfaclRes->{'other_perms'}, $userAccess_fs);
	    } else { #some groups did match, need to apply mask
		$applyMaskFlag = 1;
	    }
	}

	if ($applyMaskFlag && defined($getfaclRes->{'mask_perms'})) {
	    my $userAccess_fs_masked = {};
	    my @permTypes = ('r','w','x');
	    foreach my $curPermType (@permTypes) {
		if ($userAccess_fs->{$curPermType} && $getfaclRes->{'mask_perms'}{$curPermType}) { $userAccess_fs_masked->{$curPermType} = 1; }
	    }
	    $userAccess_fs = $userAccess_fs_masked;
	}
    }

    if (defined($webAclHash)) {
	if (defined($webAclHash->{'u'}{$username})) {
	    addPerms($webAclHash->{'u'}{$username},$userAccess_web);
	} else {
	    my $group_access_subhash = $webAclHash->{'g'} || {};
	    while (my ($groupName, $groupAccess) = each %$group_access_subhash) {
		my $groupMembersHash = $Config::web_groups->{$groupName};
		if (($groupName eq $allUsersWebAccessGroup) || ($groupMembersHash && $groupMembersHash->{$username})) {
		    addPerms($groupAccess, $userAccess_web);
		}
	    }
	}
    }

    map { $userAccess->{$_} = 1; } (keys %$userAccess_fs, keys %$userAccess_web);

    return($userAccess, $userAccess_fs, $userAccess_web);
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


sub parseGetfaclRes {

    my ($getfaclResTxt) = @_;

    my @getfaclLines = map { rem_ws($_); } split /\n/,$getfaclResTxt;

    my $getfaclRes = {};

    for (my $i=0; $i<@getfaclLines; $i++) {
	my $curLine = $getfaclLines[$i];
	if ($curLine =~ m/^\# owner\: (.+)$/) {
	    $getfaclRes->{'owner'} = $1;
	} elsif ($curLine =~ m/^\# group\: (.+)$/) {
	    $getfaclRes->{'group'} = $1;
	} elsif ($curLine =~ m/^\# file\: (.+)$/) {
	    $getfaclRes->{'file'} = $1;
	} elsif ($curLine =~ m/^([^\:]+)\:([^\:]*)\:(.+)$/) {
	    my $curPermsType = $1;
	    my $curPermsUserOrGroup = $2;
	    my $curPerms = $3;
	    my $curPermsHash = {};
	    map { $curPermsHash->{$_} = 1; } grep { $_ ne '-'; } split //, $curPerms;
	    if ($curPermsType eq 'user') {
		if (empty($curPermsUserOrGroup)) {
		    $getfaclRes->{'owner_perms'} = $curPermsHash;
		} else {
		    $getfaclRes->{'extended_perms'}{'u'}{$curPermsUserOrGroup} = $curPermsHash;
		}
	    } elsif ($curPermsType eq 'group') {
		if (empty($curPermsUserOrGroup)) {
		    $getfaclRes->{'group_perms'} = $curPermsHash;
		} else {
		    $getfaclRes->{'extended_perms'}{'g'}{$curPermsUserOrGroup} = $curPermsHash;
		}
	    } elsif (($curPermsType eq 'other') && empty($curPermsUserOrGroup)) {
		$getfaclRes->{'other_perms'} = $curPermsHash;
	    } elsif (($curPermsType eq 'mask') && empty($curPermsUserOrGroup)) {
		$getfaclRes->{'mask_perms'} = $curPermsHash;
	    }
	}
    }

    return($getfaclRes);
}

sub searchUg {

#    my $search_ug_fs_or_web;
#    my $search_ug_user_or_group;
#    my $search_ug_search_text;
#    my $callback;

    if ($search_ug_fs_or_web eq 'fs') {
	if ($search_ug_user_or_group eq 'user') {
	    my $users = getFsUsers();
	    my @matchingUsers = keys %$users;
	    if (!empty($search_ug_search_text)) {
		@matchingUsers = grep { /${search_ug_search_text}/i; } @matchingUsers;
	    }

	    print $q->header('application/json');
	    if (defined($callback)) {
		print "${callback}(";
	    }
	    print to_json({ 'success' => JSON::true, 'results' => \@matchingUsers });
	    if (defined($callback)) {
		print ");";
	    }
	    exit;
	} elsif ($search_ug_user_or_group eq 'group') {
	    my $groups = getFsGroups();
	    my @matchingGroups = keys %$groups;
	    if (!empty($search_ug_search_text)) {
		@matchingGroups = grep { /${search_ug_search_text}/i; } @matchingGroups;
	    }

	    print $q->header('application/json');
	    if (defined($callback)) {
		print "${callback}(";
	    }
	    print to_json({ 'success' => JSON::true, 'results' => \@matchingGroups });
	    if (defined($callback)) {
		print ");";
	    }
	    exit;
	}
    } elsif ($search_ug_fs_or_web eq 'web') {
	if ($search_ug_user_or_group eq 'user') {
	    my $redirectUrl = $Config::ldapSearchServiceUrl;
	    my @redirectParams;
	    if (!empty($search_ug_search_text)) { push @redirectParams, "search_text=${search_ug_search_text}"; }
	    if (!empty($callback)) { push @redirectParams, "callback=${callback}"; }
	    if (@redirectParams) {
		$redirectUrl .= "?" . join("&",@redirectParams);
	    }
	    print $q->redirect($redirectUrl);
	    exit;
	} elsif ($search_ug_user_or_group eq 'group') {
	    my @matchingGroups = ($allUsersWebAccessGroup, keys %$Config::web_groups);
	    if (!empty($search_ug_search_text)) {
		@matchingGroups = grep { /${search_ug_search_text}/i; } @matchingGroups;
	    }

	    print $q->header('application/json');
	    if (defined($callback)) {
		print "${callback}(";
	    }
	    print to_json({ 'success' => JSON::true, 'results' => \@matchingGroups });
	    if (defined($callback)) {
		print ");";
	    }
	    exit;
	}
    }

}


#query LDAP to get user's info
sub getUserLdapInfo {

    my ($uid) = @_;

    my $server = $Config::ldapServer;
	
    # Connect to LDAP server
    my $ldap = Net::LDAP->new($server);
    my $linfo = $ldap->bind(dn => "ou=People, l=Americas, o=bms.com");

    my $msg = $ldap->search(base => "o=bms.com",
			    filter => "(&(bmsentaccountstatus=Enabled)(uid=$uid))",
			    scope => "subtree");
    $ldap->unbind;
    return (0,"Error getting LDAP attrs for uid '$uid'") if ! $msg;
    return (0,"Error getting attrs for uid '$uid'\n" . $msg->error) if $msg->code;

    return (0) if ! $msg->count;
    
    my $entry = $msg->pop_entry();
    return (0,"No entry getting attrs for uid '$uid'") if ! $entry;

    return(1,$entry);

}

sub sendMail {

    my ($fromEmail, $userEmail, $ccText, $subjectTxt, $sendmailTxt) = @_;

    if (empty($fromEmail)) { $fromEmail = $Config::primary_admin_email; }

    my $sm = new SendMail($Config::mailHost);
    $sm->From($fromEmail);
    $sm->ReplyTo($fromEmail);
    $sm->Subject($subjectTxt);
    my @toArr = map { rem_ws($_); } split /,/,$userEmail;
    $sm->To(@toArr);

    if (!empty($ccText)) {
	my @ccArr = map { rem_ws($_); } split /,/,$ccText;
	$sm->Cc(@ccArr);
    }
    $sm->setMailHeader('Content-type','text/html; charset="iso-8859-1');
    $sm->setMailBody($sendmailTxt);

    if ($sm->sendMail() != 0) {
	return 0; #success
    } else {
	return 1; #failed
    }

}

sub empty {

    my ($val) = @_;

    if (!defined($val) || ($val =~ m/^\s*$/)) {
	return 1;
    } else {
	return 0;
    }
}

sub rem_ws {

    my ($val) = @_;

    if (!defined($val)) { return ""; }

    $val =~ s/^\s+//;
    $val =~ s/\s+$//;

    return($val);
}

sub printHeader {

    my ($mimeType) = @_;

    if (!$nocgi) { #access via web/Apache CGI
	print $q->header($mimeType);
    }
}

sub setParams {

    my ($errObj) = @_;

    if (defined($errObj)) {
	if (!empty($a)) { $errObj->{'a'} = $a; }
	if (!empty($fs)) { $errObj->{'fs'} = $fs; }
	if (!empty($stage)) { $errObj->{'stage'} = $stage; }
	if (!empty($mode)) { $errObj->{'mode'} = $mode; }
	if (!empty($dirPath)) { $errObj->{'dir_path'} = $dirPath; }
	if (!empty($targetPath)) { $errObj->{'target_path'} = $targetPath; }
	if (!empty($shareUsers)) { $errObj->{'share_user'} = $shareUsers; }
	if (!empty($base)) { $errObj->{'base'} = $base; }
	if (!empty($eacl)) { $errObj->{'eacl'} = $eacl; }
	if (!empty($webeacl)) { $errObj->{'webeacl'} = $webeacl; }
	if (!empty($filePath)) { $errObj->{'file_path'} = $filePath; }
	if (!empty($disposition)) { $errObj->{'disposition'} = $disposition; }
	if (!empty($recursive)) { $errObj->{'recursive'} = $recursive; }
	if (!empty($stashFileName)) { $errObj->{'stash_file'} = $stashFileName; }
	if (!empty($newPath)) { $errObj->{'new_path'} = $newPath; }
	if (!empty($no_email)) { $errObj->{'no_email'} = $no_email; }
	if (!empty($user)) { $errObj->{'user'} = $user; }
	if (!empty($current_user)) { $errObj->{'current_user'} = $current_user; } #The SiteMinder authenticated user accessing this page.
	if (!empty($search_ug_fs_or_web)) { $errObj->{'search_ug_fs_or_web'} = $search_ug_fs_or_web; }
	if (!empty($search_ug_user_or_group)) { $errObj->{'search_ug_user_or_group'} = $search_ug_user_or_group; }
	if (!empty($search_ug_search_text)) { $errObj->{'search_ug_search_text'} = $search_ug_search_text; }
	if (!empty($user_sshkey)) { $errObj->{'user_sshkey_defined'} = JSON::true; } else { $errObj->{'user_sshkey_defined'} = JSON::false; }
	if (!empty($user_password)) { $errObj->{'user_password_defined'} = JSON::true; } else { $errObj->{'user_password_defined'} = JSON::false; }
	if (!empty($callback)) { $errObj->{'callback'} = $callback; }
	return;
    }

    if ($nocgi) { #called from command line
	GetOptions ("a=s"                     => \$a,
		    "fs=s"                    => \$fs,
		    "stage=s"                 => \$stage,
		    "mode=s"                  => \$mode,
		    "dir_path=s"              => \$dirPath,
		    "target_path=s"           => \$targetPath,
		    "share_users=s"           => \$shareUsers,
		    "base=s"                  => \$base,
		    "eacl=s"                  => \$eacl,
		    "webeacl=s"               => \$webeacl,
		    "file_path=s"             => \$filePath,
		    "disposition=s"           => \$disposition,
		    "recursive=s"             => \$recursive,
		    "direct_file_path=s"      => \$directFilePath, #only for CLI access, direct path in file system to file to stash
		    "stash_file=s"            => \$stashFileName,
		    "new_path=s"              => \$newPath,
		    "no_email=s"              => \$no_email,
		    "user=s"                  => \$user,
	            "current_user=s"          => \$current_user,
	            "search_ug_fs_or_web"     => \$search_ug_fs_or_web,
	            "search_ug_user_or_group" => \$search_ug_user_or_group,
	            "search_ug_search_text"   => \$search_ug_search_text,
	            "user_sshkey"             => \$user_sshkey,
	            "user_pasword"            => \$user_password,
		    "callback"                => \$callback)
	    or cgi_die_json("Error in command line arguments\n");
    } else {
	$a = $q->param('a');
	$fs = $q->param('fs');
	$stage = $q->param('stage');
	$mode = $q->param('mode');
	$dirPath = $q->param('dir_path');
	$targetPath = $q->param('target_path');
	$shareUsers = $q->param('share_users');
	$base = $q->param('base');
	$eacl = $q->param('eacl');
	$webeacl = $q->param('webeacl');
	$filePath = $q->param('file_path');
	$disposition = $q->param('disposition');
	$recursive = $q->param('recursive');
	$stashFileName = !empty($q->param('stash_file')) ? $q->param('stash_file') . '' : ''; #uploaded file, actually returns some weird hash that prints as string; to make actual string, concat with empty string.
	$newPath = $q->param('new_path');
	$no_email = $q->param('no_email');
	$user = $q->param('user');
	$current_user = Config::getCurrentUser();
	$search_ug_fs_or_web = $q->param('search_ug_fs_or_web');
	$search_ug_user_or_group = $q->param('search_ug_user_or_group');
	$search_ug_search_text = $q->param('search_ug_search_text');
	$user_sshkey = $q->param('user_sshkey');
	$user_password = $q->param('user_password');
	$callback = $q->param('callback');
    }
    $singleQuoteInPathsFlag = 0;
    if (!empty($dirPath)) { my $substCnt = $dirPath =~ s/__SQ__|\'/\'/g; if ($substCnt > 0) { $singleQuoteInPathsFlag = 1;} }
    if (!empty($targetPath)) { my $substCnt = $targetPath =~ s/__SQ__|\'/\'/g; if ($substCnt > 0) { $singleQuoteInPathsFlag = 1;} }
    if (!empty($filePath)) { my $substCnt = $filePath =~ s/__SQ__|\'/\'/g; if ($substCnt > 0) { $singleQuoteInPathsFlag = 1;} }
    if (!empty($newPath)) { my $substCnt = $newPath =~ s/__SQ__|\'/\'/g; if ($substCnt > 0) { $singleQuoteInPathsFlag = 1;} }
    if (!empty($stashFileName)) { my $substCnt = $stashFileName =~ s/__SQ__|\'/\'/g; if ($substCnt > 0) { $singleQuoteInPathsFlag = 1;} }

}

###CODE SCRAPS
=head

#    print "Content-Type: text/plain\n\n"; ###AKS DEBUG
#    print Dumper($pathInfo_full_info) . "\n"; ###AKS DEBUG
#    exit; ###AKS DEBUG

#    print "Content-Type: text/plain\n\n"; ###AKS DEBUG
#    print Dumper($perms) . "\n"; ###AKS DEBUG
#    print "------\n"; ###AKS DEBUG
#    print Dumper($pathInfo_full_info) . "\n"; ###AKS DEBUG
#    exit; ###AKS DEBUG

#    if ((!empty($dirPath) && ($dirPath =~ m/\'/)) ||
#	(!empty($targetPath) && ($targetPath =~ m/\'/)) ||
#	(!empty($filePath) && ($filePath =~ m/\'/)) ||
#	(!empty($newPath) && ($newPath =~ m/\'/)) ||
#	(!empty($stashFileName) && ($stashFileName =~ m/\'/))) {
#	$singleQuoteInPathsFlag = 1;
#    } else {
#	$singleQuoteInPathsFlag = 0;
#    }

#old code from in Share:


#    my $updateWebEaclBashScriptTxt = "";
#    my @shareUsersArr = map { rem_ws($_); } split /,/,$shareUsers;
#    my ($perms,$faclResTxt, $fattrResTxt) = getPerms($dirPath, $recursive);
#    while (my ($file, $filePerms) = each %$perms) {
#	my $webAclHash = $filePerms->{'web_perms'} || {};
#	my $addedNewUserFlag = 0;
#	for my $curUser (@shareUsersArr) { if (!$webAclHash->{'u'}{$curUser}{'r'}) { $webAclHash->{'u'}{$curUser}{'r'} = 1; $addedNewUserFlag = 1; } }
#	if ($addedNewUserFlag) {
#	    my $webeacl = eacl_hash_to_str($webAclHash);
#	    my $setFattrCmd = "setfattr -x user.webeacl '${file}';\n";
#	    if (!empty($webeacl)) {
#		$setFattrCmd = "setfattr -n user.webeacl -v '${webeacl}' '${file}';\n",
#	    }
#	    $updateWebEaclBashScriptTxt .= $setFattrCmd;
#	}
#    }


#And don't need getPerms anymore, pathInfo does its functionality
sub getPerms {

    my ($dirPath, $recursive) = @_;

#    my $recursive = 1; ###flag telling whether to execute recursively, or not (i.e. just directly and only on the specified $dirPath)
    my $findNotRecurs = " -maxdepth 0";
    if ($recursive) { $findNotRecurs = ""; }
    my $faclRecurs = " -R";
    if (!$recursive) { $faclRecurs = ""; }
    my $recursTxt = " recursively";
    if (!$recursive) { $recursTxt = ""; }

    if (empty($dirPath)) { $dirPath = ''; }

    $dirPath =~ s/\/+$//;
    my $fullPath = $fsRoot . "/" . $dirPath;

    my $perms = {};

    my $retVal;
    $retVal = evalOrDie({"cmd" => "getfacl${faclRecurs} -p '$fullPath'",
			 "parseJsonFlag" => 0,
			 "msgIfErr" => "Error getting file system eacl for $dirPath${recursTxt} in getPerms"});
    my $faclResTxt = $retVal->{'res'};
    my @faclResSections = split/\n+\s*\n+/, $faclResTxt;
    foreach my $curFaclResSection (@faclResSections) {
	my $curFaclRes = parseGetfaclRes($curFaclResSection);
	my $file = $curFaclRes->{'file'};
	$perms->{$file} = $curFaclRes;
    }

    #find . -exec getfattr -n user.webeacl '{}' \;
    #Actually, getfattr has recursive option too, e.g.: getfattr -R -n user.webeacl --absolute-names /stash/results/dev/smitha26
    $retVal = evalOrDie({"cmd" => "getfattr${faclRecurs} -d --absolute-names '${fullPath}'",
			 "parseJsonFlag" => 0,
			 "msgIfErr" => "Error getting web eacl for $dirPath${recursTxt} in getPerms"});
    my $fattrResTxt = $retVal->{'res'};
    my @fattrResSections = split/\n+\s*\n+/, $fattrResTxt;
    foreach my $curFattrResSection (@fattrResSections) {
	my ($attrVals, $file) = parseGetFattrRes(rem_ws($curFattrResSection));
	my $webAcl = $attrVals->{'user.webeacl'};
	my $webAclHash = {};
	if (!empty($webAcl)) {
	    $webAclHash = eacl_str_to_hash($webAcl);
	}
	$perms->{$file}{'web_perms'} = $webAclHash;
    }

    return($perms,$faclResTxt, $fattrResTxt);

}


    my $map_to_stdout = $args->{'map_to_stdout'}; #if true, map the stdout of the remote SSH call to this script's STDOUT
    my $map_to_stderr = $args->{'map_to_stderr'}; #if true, map the stderr of the remote SSH call to this script's STDERR
	if ($map_to_stdout) { push @sshOpts, ('default_stdout_fh' => *STDOUT); }
	if ($map_to_stderr) { push @sshOpts, ('default_stderr_fh' => *STDERR); }



	eval {
	    if (!empty($fsPort)) {
		$ssh = Net::OpenSSH->new($fsHost,
					 'user' => $remoteSshUser,
					 'port' => $fsPort,
					 'master_opts' => [-o => "StrictHostKeyChecking=no"],
					 'key_path' => $remoteSshKeyfile);
	    } else {
		$ssh = Net::OpenSSH->new($fsHost,
					 'user' => $remoteSshUser,
					 'master_opts' => [-o => "StrictHostKeyChecking=no"],
					 'key_path' => $remoteSshKeyfile);
	    }
	};



    #if (!empty($dirPath)) { $dirPath =~ s/'/'\\''/g; }
    #if (!empty($targetPath)) { $targetPath =~  s/'/'\\''/g; }
    #if (!empty($filePath)) { $filePath =~  s/'/'\\''/g; }
    #if (!empty($newPath)) { $newPath =~  s/'/'\\''/g; }
    #if (!empty($stashFileName)) { $stashFileName =~  s/'/'\\''/g; }

#my $cmd = handleSingleQuotesInCmd("'pre's value' getfacl '/path/to/jon's powerpoint deck.ppt' -v -t '/another/path/to/copy of jon's ppt deck.ppt' -x 'x mark's the spot'; getfacl '/this/one/hits/the/spot's.txt';\nsetfattr -n user.webeacl -v 'u:smitha26:r' '/stash/results/dev/smitha26/anotherdir/Andrew's cool file.txt';\nls -la\n");
#print "$cmd\n";
#exit; ### AKS DEBUG


print Dumper(\@matches) . "\n"; print "$cmd\n"; exit;

    my @cmdSplit = split /( \'.+?\' | \'.+?\';)/, ' ' . $cmd . ' ';
    for (my $i=0; $i<@cmdSplit; $i++) {
       my $curCmdPart = $cmdSplit[$i];
       if ($curCmdPart =~ m/ \'(.+)\' /) {
          my $midPart = $1;
          $midPart =~ s/'/'\\''/g;
	  $cmdSplit[$i] = " '${midPart}' ";
       } elsif ($curCmdPart =~ m/ \'(.+)\';/) {
          my $midPart = $1;
          $midPart =~ s/'/'\\''/g;
	  $cmdSplit[$i] = " '${midPart}';";
       }
    }
    $cmd = rem_ws(join("", @cmdSplit));



#    if ($singleQuotesFlag) {
#	$updateWebEaclBashScriptTxt = join("\n", map { handleSingleQuotesInCmd($_); } split /\n/,$updateWebEaclBashScriptTxt);
#    }

=cut
