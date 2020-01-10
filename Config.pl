package Config;

#Set to 1 to enable debugging code sections (e.g. to send error emails to admin, etc.)
our $DEBUG = 0;

#Configuration for the different managed file systems.
#To use other than default, just add param fs=<FS> to the
#simple_stash.cgi or stash_ui URLS, e.g. fs=local_test
#Modify these to match your own file systems that you'd
#like to be able to access.
#Descriptions of fields:
#"host" -> The domain name of the server where the file system is
#"port" -> SSH port of the server (set this if not default port)
#"root" -> The root directory of the managed file system on "host"
#"user" -> user ID of a "file system" user, who is presumed
#          to be able to SSH to "host" and to
#          have 'rx' access to all dirs and files of
#          the managed file system. This account will be
#          used if the user doesn't provide their own
#          SSH credentials (i.e. password or SSH private key),
#          primarly to enable "web only" access to users who
#          don't have accounts on "host", e.g. collaborators
#          with whom you might want to share files/dirs with.
#"keyfile" -> Full path to the private SSH key of "user", to
#             be used to execute remote SSH (file system) commands
#             on "host"
#"set_current_user" -> override the value of $current_user with this
our $managedFileSystems = { "local_test" => { "host" => "localhost", #example of managing dir on localhost server machine
					     "root" => "/tmp",
			                     "user" => "ec2_user",
					     "keyfile" => "/usr/share/httpd/.ssh/id_rsa_ec2_user" },
			   "stash_results" => { "host" => "stash-prd.pri.bms.com", #subdirectory of default example
						"root" => "/stash/results", #at the remote host
						"user" => "irods", #FS user to use to access if user doesn't provide creds
						"keyfile" => "/usr/share/httpd/.ssh/id_rsa_irods_user" },
			   "default" => { "host" => "stash-prd.pri.bms.com", #default fs if no fs=<FS> param given
					  "root" => "/stash", #at the remote host
					  "user" => "irods",
					  "keyfile" => "/usr/share/httpd/.ssh/id_rsa_irods_user" },
			   "someother" => { "host" => "someotherserver.com",
					    "port" => 2222,
					    "set_current_user" => "someotheruser", #always use this as $current_user
					    "root" => "", #at the remote host
					    "user" => "so",
					    "keyfile" => "/home/otheruser/id_rsa" }

                         };

#You can define custom "web groups" to allow web-based access to users through these groups:
our $web_groups = { 'BLAHGROUP' => { 'smitha26' => 1, 'russom' => 1 },
		    'COOLGROUP' => { 'smitha26' => 1, 'russom' => 1, 'tilfordc' => 1, 'riosca' => 1, 'limje' => 1 } };

#These users are allowed to access in 'admin' mode;
#currently not used, but could be in future
our $adminUsers = { 'smitha26' => 1,
		    'russom' => 1,
		    'riosca' => 1 };

#Error emails will go to this email address
our $primary_admin_email = 'andrew.smith1@bms.com';

our $mailHost = "mailhost.bms.com"; #Change to your mail host
our $ldapServer = "key.pri.bms.com"; #Change to your LDAP server

our $ldapSearchServiceUrl = 'searchLdap_direct.cgi';

our $ldapServer = "key.pri.bms.com"; #Change to domain of your LDAP server
our $ldap_bindDn = "ou=People, l=Americas, o=bms.com"; #Change to your LDAP bind dn
our $ldap_searchBase = "o=bms.com"; #Change to your LDAP search base
our $ldap_searchFilter = "(&(bmsentaccountstatus=Enabled)(|(uid=\*__SEARCH_TEXT__\*)(cn=\*__SEARCH_TEXT__\*)))"; #Change to your LDAP search filter
our $ldap_searchScope = "subtree"; #Change to your LDAP search scope
our $ldapFieldMap = { 'mail' => 'mail', #change value to your LDAP field that gives email address, e.g. fred.jones@example.com
		     'cn' => 'cn', #change value to your LDAP field that gives full name, e.g. Fred Jones
		     'uid' => 'uid' }; #change value to your LDAP field that gives user's user ID, e.g. jonesf

#The system assumes there is an authenticated user and
#that user's LDAP ID/UID can be securely determined.
#Redefine this function to get the user's identity,
#if necessary.
sub getCurrentUser {

    my $current_user = $ENV{'HTTP_UID'}; #The authenticated user accessing this page (e.g. from SiteMinder)

    return($current_user);

}

1;
