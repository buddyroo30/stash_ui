# Stash Web User Interface (UI)
## File Explorer-like Web Interface to Remote File Systems

The Stash Web UI consists of a web UI frontend (using [jQuery](http://jquery.com), [Bootstrap](http://getbootstrap.com), [jsTree](http://jstree.com), and others) and a backend service layer (in Perl) that the web UI accesses. The system allows end users to interact with remote file systems in a File Explorer like way. Users can provide their credentials (password or private SSH key enabling access to the remote file system's server) in order to perform, via remote SSH commands to the file system server, file system actions (i.e. view and modify ACLs, download/view files, etc.) at the remote file system. Users can effectively do through the web UI file system commands like *ls*, *getfacl*, *setfacl*, *chmod*, etc. in a more intuitive way.

In addition to dealing with base and [POSIX extended ACL](https://www.usenix.org/legacy/publications/library/proceedings/usenix03/tech/freenix03/full_papers/gruenbacher/gruenbacher_html/main.html), the system adds a novel access-control layer called "web access" where users can effectively share and make accessible (think OneDrive share) files and directories (in read-only, access-controlled manner) on the remote file system to other users who might not have accounts on the file system's server, e.g. collaborators; only "web access" rules will be considered for users who don't provide password or SSH private key when accessing the system, while all access rules (base and extended ACLs, and web access) will be considered for users who do provide them.

Note that because users' passwords or private SSH keys are being sent to the web server (only stored and used transiently there on behalf of the user), the system should be run with SSL/HTTPS. The system has been used at my work for our analysts to easily store, manage and access results from analyses (e.g. [Knitr](https://yihui.org/knitr/) output reports, etc.) and to share those with collaborators.

## Installation/Setup

**Prerequisites**: The Perl backend service scripts have a few module requirements that you might have to install first: CGI, Getopt::Long, JSON, URI::Escape, File::Temp, File::Basename, Net::LDAP, SendMail, and Net::OpenSSH. If you don't have these you should install them first, e.g. using [cpanm](http://www.cpan.org/modules/INSTALL.html). The JavaScript dependencies (Bootstrap, jQuery, etc.) are simply included as CDN links in index.html, so you wouldn't have to install any of them.

We've run the system under the [Apache web server](https://httpd.apache.org/); the system uses [LDAP](http://ldap.com) (to enable querying for other user IDs inside the searchLdap_direct.cgi script, used in sharing and setting permissions) and we have also used it with [SiteMinder](https://www.broadcom.com/products/software/cybersecurity/identity-and-access-management/layer7-siteminder) (in order to determine the user ID of the accessing user, however the system could use alternative identity determination systems and you simply need to redefine a function inside Config.pl). To get the system running, copy the backend service scripts simple_stash.cgi, Config.pl and searchLdap_direct.cgi into your web server's executable location (e.g. /var/www/cgi-bin) and copy the contents of the stash_ui directory to a static content directory of your web server (e.g. /var/www/html). Then modify the 2 config files stash_ui/config.js and Config.pl to setup for your specific use (i.e. specify details of the remote file systems you want to manage, etc.) See the comments inside stash_ui/config.js and Config.pl for details of what needs to be specified.

Note that the main backend service script simple_stash.cgi can also be used as a command line interface (CLI) to perform actions on a file system. For example:

```
unset HTTP_HOST; simple_stash.cgi -a directory_contents -stage exec -dir_path 'path/to/dir' -user_sshkey_file '<PATH TO SSH PRIVATE KEY FILE>' -current_user <USER ID>"; #unset HTTP_HOST so simple_stash knows we're executing in CLI mode
```

**Coming Soon:** We plan to release the system as a Docker image at [Docker Hub](http://hub.docker.com) to allow you simply to run the application as a Docker container.

## Screenshots of the system
### Overview/What the system can do
![Overview](/screenshots/WhatCanStashUIDo.png?raw=true "Overview")
### Providing your SSH credentials
![Providing credentials](/screenshots/ProvidingCreds.png?raw=true "Providing credentials")
### View and Edit ACL Dialog
![View and Edit ACL](/screenshots/ViewModifyEacl_screenshot.png?raw=true "View and Edit ACL")

## Contact
Please email Andrew Smith (andrewksmith@gmail.com) with any questions, feedback, feature requests, etc.
