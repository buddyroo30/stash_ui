var queryParams;
var current_user;

var inputRowCt = 0;

var tree_div_id = 'simple_stash_tree';

function getFileTypeIconClasses (file) {

    var fileType = file.split('.').pop().toLowerCase();
    var iconClass = fileTypeIconClasses[fileType];
    if (isBlank(iconClass)) {
	iconClass = 'fa fa-file'; //generic file icon
    }

    return(iconClass);

    //'icon' : 'glyphicon glyphicon-file',

}

function isBlank(str) {
    return (!str || /^\s*$/.test(str));
}

function dirname(my_path,dir_sep) {

    if (isBlank(dir_sep)) { dir_sep = '/'; }
    var prefix_path_idx = my_path.lastIndexOf(dir_sep);
    if (prefix_path_idx == -1) { //didn't occur
	return('');
    } else {
	var dir_name = my_path.substr(0, prefix_path_idx);
	return(dir_name);
    }

}

var getQueryParams = function ( url ) {

    var params = {};
    var href = url ? url : window.location.href;
    var split_arr = href.split('?');
    if (split_arr.length > 1) {
	var params_str = split_arr[1];
	var params_and_vals = params_str.split('&');
	for (var i=0; i<params_and_vals.length; i++) {
	    var cur_param_and_val = params_and_vals[i];
	    var cur_param_and_val_split = cur_param_and_val.split('=');
	    if (cur_param_and_val_split.length > 1) {
		var cur_vals_arr = params[cur_param_and_val_split[0]];
		if (!cur_vals_arr) {
		    params[cur_param_and_val_split[0]] = [];
		    cur_vals_arr = params[cur_param_and_val_split[0]];
		}
		cur_vals_arr.push(unescape(cur_param_and_val_split[1]));
	    }
	}
    }
    return(params);
};

function checkXhrFailure (xhr, thrownError, errMsg) {

    var responseTxt = xhr.responseText;
    if (!isBlank(responseTxt) &&
	responseTxt.match(smErrCheckTxt)) { //SiteMinder check failed
	location.reload(true);
    } else {
	alert(errMsg + ":" + thrownError + ',' + xhr.status);
    }
}

function addCredsAndFs (data_vals) {

   var curSettings = getSettings();

   if (!isBlank(curSettings.privateKey)) {
       data_vals['user_sshkey'] = curSettings.privateKey;
   }

   if (!isBlank(curSettings.password)) {
       data_vals['user_password'] = curSettings.password;
   }

   if (queryParams['fs']) { data_vals['fs'] = queryParams['fs'][0]; }

}

function getNextLevel (dir_path,cb) {

   var data_vals = {'dir_path': dir_path,
		    'a': 'directory_contents',
		    'stage': 'exec'};

   addCredsAndFs (data_vals);

   $.ajax({
       method: 'POST',
       url: simple_stash_service_url,
 
       // Tell jQuery we're expecting JSON
       dataType: 'json',

       'data': data_vals,
  
       // Work with the response
       success: function( response ) {

	   if (!response.success) {
	       alert('Error during directory_contents: ' + response.msg);
	       cb([]);
	   } else {
	       var nodes_arr = [];
	       var directory_contents = response.directory_contents;
	       var files_symlink_targets = response.files_symlink_targets;
	       var directory_contents_keys = Object.keys(directory_contents).sort();
	       for (var i=0; i < directory_contents_keys.length; i++) {
		   var name = directory_contents_keys[i];
		   var ftype = directory_contents[name];
		   var path;
		   if (isBlank(dir_path)) { path = name; } else { path = dir_path + '/' + name; }
		   if (ftype === 'D') { //directory
		       var cur_node = { 'text': name,
					'path': path,
					'is_dir': true,
					'children': true //setting children to true will cause jsTree to initiate another Ajax call to get node's children
			              };
		       nodes_arr.push(cur_node);
		   } else if (ftype === 'SD') { //symlink to directory
		       var cur_node = { 'text': name,
					'symlink_path': path,
					'path': files_symlink_targets[name],
					'is_dir': true,
					'is_symlink': true,
					'icon' : 'glyphicon glyphicon-link',
//					'icon' : '/stash_ui_dev/DirLink.svg',
					'a_attr' : { 'title': 'Link to Directory: ' + files_symlink_targets[name] },
					'children': true //setting children to true will cause jsTree to initiate another Ajax call to get node's children
			              };
		       nodes_arr.push(cur_node);
		   } else if (ftype === 'SF') { //symlink to file
		       var cur_node = { 'text': name,
					'symlink_path': path,
					'path': files_symlink_targets[name],
					'is_dir': false,
					'is_symlink': true,
					'icon' : 'glyphicon glyphicon-link',
//					'icon' : '/stash_ui_dev/FileLink.svg',
					'a_attr' : { 'title': 'Link to File: ' + files_symlink_targets[name] },
					'children': false
			              };
		       nodes_arr.push(cur_node);
		   } else if (ftype === 'F') { //file
		       var cur_node = { 'text': name,
					'path': path,
					'is_dir': false,
					'icon' : getFileTypeIconClasses (name),
					'children': false
			              };
		       nodes_arr.push(cur_node);
		   }
	       }
	   }

	   if (typeof cb != 'undefined') {
	       var root_node_obj = $('#' + tree_div_id).jstree().get_node('ROOT_NODE');
//	       if (isBlank(dir_path) && !root_node_obj) { //the root, is special the first time
	       if (!root_node_obj) { //the root, is special the first time
		   var root_node = { 'icon': 'glyphicon glyphicon-home',
				     //'text': dir_path,
				     'id': 'ROOT_NODE',
				     'state': { 'opened': true },
//				     'path': '',
				     'path': dir_path,
				     'is_dir': true,
				     'children': nodes_arr
			          };
		   cb([root_node]);
	       } else {
		   cb(nodes_arr);
	       }
	   } else {
	       console.log( nodes_arr );
           }
       },
       error: function (xhr, ajaxOptions, thrownError) {
	   checkXhrFailure (xhr, thrownError, "Error During getNextLevel");
       }
   });

}


function DownloadFileFunc (node) {

    var retFunc = function () {

	$('#spinner').show();

	var my_path = node.original.path;

	var data_vals = {'dir_path': my_path,
			 'a': 'determine_user_access',
			 'stage': 'exec'};
	
	addCredsAndFs (data_vals);

	$.ajax({
	    method: 'POST',
	    url: simple_stash_service_url,
 
	    // Tell jQuery we're expecting JSON
	    dataType: 'json',

	    'data': data_vals,
  
	    // Work with the response
	    success: function( response ) {
		$('#spinner').hide();
		if (!response.success) {
		    alert('Error during determine_user_access: ' + response.msg);
		} else {
		    var my_path = node.original.path;
		    if (response.user_access.r) {
			var formArgs = { 'a': 'download_file',
					 'stage': 'exec',
					 'disposition': 'attachment',
					 'file_path': my_path };
			if (!isBlank(queryParams['fs'])) { formArgs['fs'] = queryParams['fs'][0]; }
			doPostRD(formArgs);
		    } else {
			alert("Error: you do not have read access to " + my_path + " in order to download it.");
		    }
		}
	    },
	    error: function (xhr, ajaxOptions, thrownError) {
		$('#spinner').hide();
		checkXhrFailure (xhr, thrownError, "Error During determine_user_access");
	    }
	});

    }

    return(retFunc);

}

function DownloadDirLinkFunc (node) {

    var retFunc = function () {
	var my_path = node.original.path;
	//var download_url = simple_stash_service_url + '?a=download_file&stage=exec&file_path=' + my_path;
	var download_url = window.location.origin + window.location.pathname + '?root=' + my_path + '&postrd=download_dir';
	var fsTxt = '';
	if (queryParams['fs']) { fsTxt = '&fs=' + queryParams['fs'][0]; }
	download_url += fsTxt;
	$("#downloadLink").html(download_url);
	$("#downloadLink").attr('href',download_url);
	$("#downloadLinkModal").modal();
    }

    return(retFunc);
}


function DownloadDirFunc (node) {

    var retFunc = function () {

	$('#spinner').show();

	var my_path = node.original.path;

	var data_vals = {'dir_path': my_path,
			 'a': 'check_zip_access',
			 'stage': 'exec'};

	addCredsAndFs (data_vals);

	$.ajax({
	    method: 'POST',
	    url: simple_stash_service_url,
 
	    // Tell jQuery we're expecting JSON
	    dataType: 'json',

	    'data': data_vals,
  
	    // Work with the response
	    success: function( response ) {
		$('#spinner').hide();
		if (!response.success) {
		    alert('Error during check_zip_access: ' + response.msg);
		} else {
		    if (response.has_zip_access) {
			var formArgs = { 'a': 'download_dir',
					 'stage': 'exec',
					 'dir_path': node.original.path };
			if (!isBlank(queryParams['fs'])) { formArgs['fs'] = queryParams['fs'][0]; }
			doPostRD(formArgs);
		    } else {
			alert("Error: you do not have read access to download '" + my_path + "' :" + response.msg);
		    }
		}
	    },
	    error: function (xhr, ajaxOptions, thrownError) {
		$('#spinner').hide();
		checkXhrFailure (xhr, thrownError, "Error During check_zip_access");
	    }
	});

    }

    return(retFunc);

}

function eacl_str_to_hash (eacl) {

    if (isBlank(eacl)) { eacl = ''; }

    var eacl_hash = {};
    var indivEacl = eacl.split(',');
    for (var i=0; i < indivEacl.length; i++) {
	var curEacl = indivEacl[i];
	var curEaclParts = curEacl.split(':');
	var type = curEaclParts[0];
	var userOrGroupName = curEaclParts[1];
	var perms = curEaclParts[2];
	var permsArr = [];
	if (!isBlank(perms)) {
	    permsArr = perms.split('');
	}
	var access_hash = {};
	for (var j=0; j< permsArr.length; j++) {
	    var curPerm = permsArr[j]; 
	    access_hash[curPerm] = 1;
	}
	var typeHash = eacl_hash[type];
	if (typeof typeHash == 'undefined') {
	    eacl_hash[type] = {};
	    typeHash = eacl_hash[type];
	}
	typeHash[userOrGroupName] = access_hash;
    }

    return(eacl_hash);

}


function ShowEditEacl (node) {

    var retFunc = function () {

	$('#spinner').show();

	var my_path = node.original.path;

	var data_vals = {'dir_path': my_path,
			 'a': 'show_eacl',
			 'stage': 'exec'};


	addCredsAndFs (data_vals);

	$.ajax({
	    method: 'POST',
	    url: simple_stash_service_url,
 
	    // Tell jQuery we're expecting JSON
	    dataType: 'json',

	    'data': data_vals,
  
	    // Work with the response
	    success: function( response ) {
		if (!response.success) {
		    alert('Error during show_eacl: ' + response.msg);
		} else {
		    var allEaclHash = { 'fs': response.eacl, 'web': response.webeacl, 'base': response.base };
		    initAclEntry(allEaclHash,'show-edit-acl');
		    $("#curEACL_label").html('path: ' + my_path);
		    $('#curEACL_button').off('click');
		    $("#curEACL_button").click(UpdateEACLClickFunc(node));
		    var eacl_hash = eacl_str_to_hash(response.base);
		    if (typeof eacl_hash['u'][current_user] != 'undefined') {
			$("#curEACL_button").prop('disabled', false);
		    } else {
			$("#curEACL_button").prop('disabled', true);
		    }
		    $("#showEditEaclModal").modal();
		}
		$('#spinner').hide();
	    },
	    error: function (xhr, ajaxOptions, thrownError) {
		$('#spinner').hide();
		checkXhrFailure (xhr, thrownError, "Error During show_eacl");
	    }
	});

    }

    return(retFunc);
}


function share_ac_func (req,resp) {

	$('#spinner').show();

	var data_vals = {'term': req.term, 'jqa': '1'};

	$.ajax({
	    method: 'POST',
	    url:'/cgi-bin/stash_ui_release/searchLdap_direct.cgi',
 
	    // Tell jQuery we're expecting JSON
	    dataType: 'json',

	    'data': data_vals,
  
	    // Work with the response
	    success: function( response ) {
		$('#spinner').hide();
		resp(response);
	    },
	    error: function (xhr, ajaxOptions, thrownError) {
		$('#spinner').hide();
		checkXhrFailure (xhr, thrownError, "Error During search of LDAP");
	    }
	});

}

var acSelVals = {};

function share_ac_select_func (event,ui) {

    acSelVals[ui.item.label] = ui.item;

}

function basename(path) {
   return path.split('/').reverse()[0];
}

var symlink_select_location_flag = false;

function CreateSymlinkFunc (node) {

    var retFunc = function () {

	if (symlink_select_location_flag) {
	    if (!node.original.is_dir) {
		$("#symlink_location").val('');
		$("#symlink_name").val('');
		$("#symlink_target").val('');
		$("#symlink_target").val(node.original.path);
		symlink_select_location_flag = false;
	    } else {
		var fileName = $("#symlink_target").val();
		if (isBlank(fileName)) {
		    alert("Error: please first select a symlink target!");
		    $("#symlinkModal").modal('hide');
		    return;
		}
		fileName = basename(fileName);
		$("#symlink_location").val(node.original.path);
		$("#symlink_name").val(fileName);
	    }
	} else {
	    $("#symlink_target").val(node.original.path);
	}
	$('#symlink_create_Button').off('click');
	$("#symlink_create_Button").click(CreateSymlinkClickFunc(node));
	$('#symlink_select_location_Button').off('click');
	$('#symlink_select_location_Button').click(CreateSymlinkSelectLocationFunc(node));
	$('#symlink_cancel_Button').off('click');
	$("#symlink_cancel_Button").click(CreateSymlinkCancelFunc(node));
	$("#symlinkModal").modal();

    }

    return(retFunc);
}

function CreateSymlinkCancelFunc(node) {

    var retFunc = function() {
	$("#symlink_location").val('');
	$("#symlink_name").val('');
	$("#symlink_target").val('');
	symlink_select_location_flag = false;
	$("#symlinkModal").modal('hide');
    }

    return(retFunc);

}

function CreateSymlinkSelectLocationFunc(node) {

    var retFunc = function () {
	alert("Please navigate in the Stash UI Tree to the directory where you want the symlink created, then right click and choose the 'Create Symlink' menu item again, then click 'Create' (you will also be able to optionally change the name of the symlink if desired, but the default name is the same name as the target).");
	$("#symlinkModal").modal('hide');
	symlink_select_location_flag = true;
    }

    return(retFunc);

}

function CreateSymlinkClickFunc (node) {

    var retFunc = function () {

	var slTarget = $("#symlink_target").val();
	var slFullLoc = $("#symlink_location").val() + '/' + $("#symlink_name").val();

	if (isBlank($("#symlink_name").val()) ||
	    isBlank($("#symlink_location").val())) {
	    alert("Error: You cannot have a blank value for the location and/or name of the symlink! Please click 'Select Location' to choose values for these.");
	    return;
	}

	if (slTarget === slFullLoc) {
	    alert("Error: you cannot symlink a file to itself!");
	    return;
	}


	$('#spinner').show();

	var data_vals = {'dir_path': slFullLoc,
			 'target_path': slTarget,
			 'a': 'create_symlink',
			 'stage': 'exec'};

	addCredsAndFs (data_vals);

	$.ajax({
	    method: 'POST',
	    url: simple_stash_service_url,
 
	    // Tell jQuery we're expecting JSON
	    dataType: 'json',

	    'data': data_vals,
  
	    // Work with the response
	    success: function( response ) {
		if (!response.success) {
		    alert('Error during create_symlink: ' + response.msg);
		} else {
		    $("#symlinkModal").modal('hide');
		    $("#symlink_location").val('');
		    $("#symlink_name").val('');
		    $("#symlink_target").val('');
		    symlink_select_location_flag = false;
		    $('#' + tree_div_id).jstree().refresh_node(node);
		    $('#' + tree_div_id).jstree().open_node(node);

		}
		$('#spinner').hide();
	    },
	    error: function (xhr, ajaxOptions, thrownError) {
		$('#spinner').hide();
		checkXhrFailure (xhr, thrownError, "Error During create_dir");
	    }
	});
    }

    return(retFunc);

}

function ShareFunc (node) {

    var retFunc = function () {

	var my_path = node.original.path;

	$("#share_label").html('path: ' + my_path);
	$('#share_button').off('click');
	$("#share_button").click(ShareClickFunc(node));
	$("#shareModal").modal();

    }

    return(retFunc);
}

function ShareClickFunc (node) {

    var retFunc = function () {

	$('#spinner').show();
	var my_path = node.original.path;
	var shareWithUsers = $('#share_with_users').val().split(',');
	shareWithUsers = $.grep(shareWithUsers, function (val, i) {
	    return !isBlank(acSelVals[val])
	});

	var shareWithUsers_un = $.map( shareWithUsers, function( val, i ) {
	    return(acSelVals[val].userid);
	});

	var data_vals = {'dir_path': my_path,
			 'a': 'share',
			 'share_users': shareWithUsers_un.join(","),
			 'recursive': '1',
			 'stage': 'exec'};

	addCredsAndFs (data_vals);

	$.ajax({
	    method: 'POST',
	    url: simple_stash_service_url,
 
	    // Tell jQuery we're expecting JSON
	    dataType: 'json',

	    'data': data_vals,
  
	    // Work with the response
	    success: function( response ) {
		if (!response.success) {
		    alert('Error during share: ' + response.msg);
		} else {
		    $("#shareModal").modal('hide');
		}
		$('#spinner').hide();
	    },
	    error: function (xhr, ajaxOptions, thrownError) {
		$('#spinner').hide();
		checkXhrFailure (xhr, thrownError, "Error During share");
	    }
	});
    }

    return(retFunc);

}


function UpdateEACLClickFunc (node) {

    var retFunc = function () {

	$('#spinner').show();
	var my_path = node.original.path;

	var eaclValsHash = getAclVals (inputRowCt,'show-edit-acl');
	if (!isBlank(eaclValsHash['err_msg'])) { alert(eaclValsHash['err_msg']); $('#spinner').hide(); return; }
	var eaclStr = '';
	if (eaclValsHash.fs.length > 0) { eaclStr = eaclValsHash.fs.join(","); }
	var webeaclStr = '';
	if (eaclValsHash.web.length > 0) { webeaclStr = eaclValsHash.web.join(","); }
	var baseStr = '';
	if (eaclValsHash.base.length > 0) { baseStr = eaclValsHash.base.join(","); }

	var recursive = '0';
	if ($('#curEACL_recursive').is(":checked")) { recursive = '1'; }

	var data_vals = {'dir_path': my_path,
			 'a': 'modify_eacl',
			 'eacl': eaclStr,
			 'webeacl': webeaclStr,
			 'base': baseStr,
			 'recursive': recursive,
			 'stage': 'exec'};

	addCredsAndFs (data_vals);

	$.ajax({
	    method: 'POST',
	    url: simple_stash_service_url,
 
	    // Tell jQuery we're expecting JSON
	    dataType: 'json',

	    'data': data_vals,
  
	    // Work with the response
	    success: function( response ) {
		if (!response.success) {
		    alert('Error during modify_eacl: ' + response.msg);
		} else {
		    $("#showEditEaclModal").modal('hide');

		}
		$('#spinner').hide();
	    },
	    error: function (xhr, ajaxOptions, thrownError) {
		$('#spinner').hide();
		checkXhrFailure (xhr, thrownError, "Error During modify_eacl");
	    }
	});

    }

    return(retFunc);

}

function DeleteFunc (node) {

    var retFunc = function () {
	$('#spinner').show();
	var my_path = node.original.path;

	if (!confirm("Are you sure you want to delete '" + my_path + "'?")) {
	    $('#spinner').hide();
	    return;
	}

	var data_vals = {'dir_path': my_path,
			 'a': 'delete',
			 'stage': 'exec'};

	addCredsAndFs (data_vals);

	$.ajax({
	    method: 'POST',
	    url: simple_stash_service_url,
 
	    // Tell jQuery we're expecting JSON
	    dataType: 'json',

	    'data': data_vals,
  
	    // Work with the response
	    success: function( response ) {
		if (!response.success) {
		    alert('Error: ' + response.msg);
		} else {
		    var parent_node_id = $('#' + tree_div_id).jstree().get_parent(node);
		    if ((parent_node_id === '#') && !isBlank(my_path)) { //user had chosen a new root (i.e. not true root node)
			var up_level = dirname(my_path);
			document.location = "?root=" + up_level;
		    } else {
			$('#' + tree_div_id).jstree().delete_node(node);
		    }
		}
		$('#spinner').hide();
	    },
	    error: function (xhr, ajaxOptions, thrownError) {
		$('#spinner').hide();
		checkXhrFailure (xhr, thrownError, "Error During Delete");
	    }
	});

    }

    return(retFunc);

}

function CreateDirFunc (node) {

    var retFunc = function () {
	var my_path = node.original.path;

	$('#createDir_button').off('click');
	$("#createDir_button").click(createDirClickFunc(node));
	initAclEntry ({ 'base': 'o:OTHER:r,g:bioinfo:r,u:' + current_user + ':rwx', 'web': 'g:EVERYONE:r'},'create-dir');

	$("#createDirModal").modal()
    }

    return(retFunc);
}

function createDirClickFunc (node) {

    var retFunc = function () {

	$('#spinner').show();
	var my_path = node.original.path;

	var new_dir = $("#createDirPath").val();
	if (/\//.test(new_dir)) {
	    alert('Error: the new directory path cannot contain "/" characters');
	    return;
	}
	var new_path = my_path + '/' + new_dir;
	if (isBlank(my_path)) { //at the root
	    new_path = new_dir;
	}

	var eaclValsHash = getAclVals (inputRowCt,'create-dir');
	if (!isBlank(eaclValsHash['err_msg'])) { alert(eaclValsHash['err_msg']); $('#spinner').hide(); return; }
	var eaclStr = '';
	if (eaclValsHash.fs.length > 0) { eaclStr = eaclValsHash.fs.join(","); }
	var webeaclStr = '';
	if (eaclValsHash.web.length > 0) { webeaclStr = eaclValsHash.web.join(","); }
	var baseStr = '';
	if (eaclValsHash.base.length > 0) { baseStr = eaclValsHash.base.join(","); }


	var data_vals = {'dir_path': new_path,
			 'a': 'create_dir',
			 'base': baseStr,
			 'eacl': eaclStr,
			 'webeacl': webeaclStr,
			 'stage': 'exec'};

	addCredsAndFs (data_vals);

	$.ajax({
	    method: 'POST',
	    url: simple_stash_service_url,
 
	    // Tell jQuery we're expecting JSON
	    dataType: 'json',

	    'data': data_vals,
  
	    // Work with the response
	    success: function( response ) {
		if (!response.success) {
		    alert('Error during create_dir: ' + response.msg);
		} else {
		    $("#createDirModal").modal('hide');
		    if ($('#' + tree_div_id).jstree().is_open(node)) {
			var new_dir_node = { 'text': new_dir,
					     'path': new_path,
					     'is_dir': true,
					     'children': true //setting children to true will cause jsTree to initiate another Ajax call to get node's children
					   };
			$('#' + tree_div_id).jstree().create_node(node,new_dir_node);
		    } else {
			$('#' + tree_div_id).jstree().refresh_node(node);
			$('#' + tree_div_id).jstree().open_node(node);
		    }
		}
		$('#spinner').hide();
	    },
	    error: function (xhr, ajaxOptions, thrownError) {
		$('#spinner').hide();
		checkXhrFailure (xhr, thrownError, "Error During create_dir");
	    }
	});

    }

    return(retFunc);

}

function RenameFunc (node) {

    var retFunc = function () {
	var my_path = node.original.path;

	var init_name = node.original.text;
	if (isBlank(init_name)) {
	    init_name = my_path.substring(my_path.lastIndexOf('/')+1);
	}

	$('#newName').val(init_name);
	$('#rename_button').off('click');
	$("#rename_button").click(renameClickFunc(node));
	$("#renameModal").modal();
    }

    return(retFunc);
}

function renameClickFunc (node) {

    var retFunc = function () {

	var new_name = $("#newName").val();
	if (!confirm("Are you sure you want to rename to '" + new_name + "'?")) {
	    $("#renameModal").modal('hide');
	    return;
	} else {
	    execRenameNode (node,new_name);
	}

    }

    return(retFunc);

}

function execRenameNode (node,new_name) {

	$('#spinner').show();

	var my_path = node.original.path;

	if (/\//.test(new_name)) {
	    alert('Error: the new name cannot contain "/" characters');
	    return;
	}

	var new_path;
	var prefix_path = dirname(my_path);
	if (isBlank(prefix_path)) {
	    new_path = new_name;
	} else {
	    new_path = prefix_path + '/' + new_name;
	}

	var data_vals = {'dir_path': my_path,
			 'new_path': new_path,
			 'a': 'move',
			 'stage': 'exec'};

	addCredsAndFs (data_vals);

	$.ajax({
	    method: 'POST',
	    url: simple_stash_service_url,
 
	    // Tell jQuery we're expecting JSON
	    dataType: 'json',

	    'data': data_vals,
  
	    // Work with the response
	    success: function( response ) {
		if (!response.success) {
		    alert('Error during move: ' + response.msg);
		} else {
		    $("#renameModal").modal('hide');
		    var parent_node_id = $('#' + tree_div_id).jstree().get_parent(node);
		    var parent_node = $('#' + tree_div_id).jstree().get_node(parent_node_id);
		    if (parent_node_id === '#') { //the root, need to handle differently; see here: https://stackoverflow.com/questions/39745096/how-to-refresh-root-node-in-jstree
			if (!isBlank(my_path)) { //If the user has rooted somewhere else (i.e. not the true root)
			    document.location = "?root=" + new_path;
			} else {
			    $('#' + tree_div_id).jstree().refresh();
			}
		    } else {
			$('#' + tree_div_id).jstree().refresh_node(parent_node);
		    }
		}
		$('#spinner').hide();
	    },
	    error: function (xhr, ajaxOptions, thrownError) {
		$('#spinner').hide();
		checkXhrFailure (xhr, thrownError, "Error During move");
	    }
	});

}

function StashFileFunc (node) {

    var retFunc = function () {
	var my_path = node.original.path;

	$('#stashFile_button').off('click');
	$("#stashFile_button").click(stashFileClickFunc(node));
	initAclEntry ({ 'base': 'o:OTHER:r,g:bioinfo:r,u:' + current_user + ':rwx', 'web': 'g:EVERYONE:r'},'stash-file');
	$('#stashFile').val(''); //clear any previously chosen files
	$("#stashFileModal").modal()
    }

    return(retFunc);
}

function stashFileClickFunc (node) {

    var retFunc = function () {
	var eaclValsHash = getAclVals (inputRowCt,'stash-file');
	if (!isBlank(eaclValsHash['err_msg'])) { alert(eaclValsHash['err_msg']); return; }
	var baseStr = '';
	if (eaclValsHash.base.length > 0) { baseStr = eaclValsHash.base.join(","); }
	var eaclStr = '';
	if (eaclValsHash.fs.length > 0) { eaclStr = eaclValsHash.fs.join(","); }
	var webeaclStr = '';
	if (eaclValsHash.web.length > 0) { webeaclStr = eaclValsHash.web.join(","); }
	doFileUpload (node, $('#stashFile')[0].files[0], baseStr, eaclStr, webeaclStr);
    }

    return(retFunc);

}

function doFileUpload (node, my_file, base, eacl, webeacl) {

    $('#spinner').show();

    var my_path = node.original.path;

    if (isBlank(base)) { base = ''; }
    if (isBlank(eacl)) { eacl = ''; }
    if (isBlank(webeacl)) { webeacl = ''; }

    //See here for how to do an Ajax POST file upload:
    //https://stackoverflow.com/questions/6974684/how-to-send-formdata-objects-with-ajax-requests-in-jquery
    var fd = new FormData();    
    fd.append('stash_file', my_file);
    fd.append('dir_path', my_path);
    fd.append('a', 'stash_file');
    fd.append('stage', 'exec');
    fd.append('base', base);
    fd.append('eacl', eacl);
    fd.append('webeacl', webeacl);
    var curSettings = getSettings();
    var cur_ssconfig_sshPrivKey = curSettings.privateKey;
    var cur_ssconfig_password = curSettings.password;
    if (!isBlank(cur_ssconfig_sshPrivKey)) {
	fd.append('user_sshkey',cur_ssconfig_sshPrivKey);
    }
    if (!isBlank(cur_ssconfig_password)) {
	fd.append('user_password',cur_ssconfig_password);
    }
    if (queryParams['fs']) { fd.append('fs',queryParams['fs'][0]); }

    $.ajax({
	method: 'POST',
	url: simple_stash_service_url,
	
	// Tell jQuery we're expecting JSON
	dataType: 'json',

	data: fd,
	processData: false,
        contentType: false,
	
	// Work with the response
	success: function( response ) {
	    if (!response.success) {
		alert('Error during stash_file: ' + response.msg);
	    } else {
		$("#stashFileModal").modal('hide');
		if ($('#' + tree_div_id).jstree().is_open(node)) {
		    var new_file_path;
		    if (isBlank(my_path)) { new_file_path = my_file.name; } else { new_file_path = my_path + '/' + my_file.name; }
		    var new_file_node = { 'text': my_file.name,
					  'path': new_file_path,
					  'is_dir': false,
					  'icon' : 'glyphicon glyphicon-file',
					  'children': false
					};
		    $('#' + tree_div_id).jstree().create_node(node,new_file_node);
		} else {
		    $('#' + tree_div_id).jstree().refresh_node(node);
		    $('#' + tree_div_id).jstree().open_node(node);
		}
	    }
	    $('#spinner').hide();
	},
	error: function (xhr, ajaxOptions, thrownError) {
	    $('#spinner').hide();
	    checkXhrFailure (xhr, thrownError, "Error During stash_file");
	}
    });

}

function RootHereFunc (node) {

    var retFunc = function () {
	var my_path = node.original.path;
	var fsTxt = '';
	if (queryParams['fs']) { fsTxt = '&fs=' + queryParams['fs'][0]; }
	window.location = 'index.html?root=' + my_path + fsTxt;
    }

    return(retFunc);
}

function RefreshFunc (node) {

    var retFunc = function () {
	$('#' + tree_div_id).jstree().refresh_node(node);
	$('#' + tree_div_id).jstree().open_node(node);
    }

    return(retFunc);
}

function openFileLinkFunc(node) {

    var retFunc = function () {
	var my_path = node.original.path;
	var download_url = window.location.origin + window.location.pathname + '?root=' + my_path + '&postrd=download_file&disposition=inline';
	var fsTxt = '';
	if (queryParams['fs']) { fsTxt = '&fs=' + queryParams['fs'][0]; }
	download_url += fsTxt;
	$("#downloadLink").html(download_url);
	$("#downloadLink").attr('href',download_url);
	$("#downloadLinkModal").modal();
    }

    return(retFunc);
}

function DownloadLinkFunc (node) {

    var retFunc = function () {
	var my_path = node.original.path;
	var download_url = window.location.origin + window.location.pathname + '?root=' + my_path + '&postrd=download_file&disposition=attachment';
	var fsTxt = '';
	if (queryParams['fs']) { fsTxt = '&fs=' + queryParams['fs'][0]; }
	download_url += fsTxt;
	$("#downloadLink").html(download_url);
	$("#downloadLink").attr('href',download_url);
	$("#downloadLinkModal").modal();
    }

    return(retFunc);
}

function RootHereLinkFunc (node) {

    var retFunc = function () {
	var my_path = node.original.path;
	var root_here_url = window.location.origin + window.location.pathname + '?root=' + my_path;
	var fsTxt = '';
	if (queryParams['fs']) { fsTxt = '&fs=' + queryParams['fs'][0]; }
	root_here_url += fsTxt;
	$("#roothereLink").html(root_here_url);
	$("#roothereLink").attr('href',root_here_url);
	$("#roothereLinkModal").modal('show');
    }

    return(retFunc);
}

function testSshKey (keyWorksFunc) {

   var data_vals = {'a': 'test_ssh_key',
		    'stage': 'exec'};

   var curSettings = getSettings();
   var cur_ssconfig_sshPrivKey = curSettings.privateKey;
   if (!isBlank(cur_ssconfig_sshPrivKey)) {
       data_vals['user_sshkey'] = cur_ssconfig_sshPrivKey;
   }

   if (queryParams['fs']) { data_vals['fs'] = queryParams['fs'][0]; }

   $.ajax({
       method: 'POST',
       url: simple_stash_service_url,
 
       // Tell jQuery we're expecting JSON
       dataType: 'json',

       'data': data_vals,
  
       // Work with the response
       success: function( response ) {
	   if (!response.ssh_key_works) {
	       alert("You have provided a non-empty SSH Private key value in config which does not work. Please either set it to empty or update config to provide the correct SSH key.");
	   } else {
	       if (keyWorksFunc) { keyWorksFunc(); }
	   }
       },
       error: function (xhr, ajaxOptions, thrownError) {
	   checkXhrFailure (xhr, thrownError, "Error During testing of user provided SSH Private Key");
       }
   });

}

function testPassword (passwordWorksFunc) {

   var data_vals = {'a': 'test_ssh_key',
		    'stage': 'exec'};

   var curSettings = getSettings();
   var cur_ssconfig_password = curSettings.password;

   if (!isBlank(cur_ssconfig_password)) {
       data_vals['user_password'] = cur_ssconfig_password;
   }

   if (queryParams['fs']) { data_vals['fs'] = queryParams['fs'][0]; }

   $.ajax({
       method: 'POST',
       url: simple_stash_service_url,
 
       // Tell jQuery we're expecting JSON
       dataType: 'json',

       'data': data_vals,
  
       // Work with the response
       success: function( response ) {
	   if (!response.ssh_key_works) {
	       alert("You have provided a non-empty password value in config which does not work. Please either set it to empty or update config to provide the correct password.");
	   } else {
	       if (passwordWorksFunc) { passwordWorksFunc(); }
	   }
       },
       error: function (xhr, ajaxOptions, thrownError) {
	   checkXhrFailure (xhr, thrownError, "Error During testing of user provided password");
       }
   });

}


//See here for setting up custom jstree context menus:
//https://stackoverflow.com/questions/4559543/configuring-jstree-right-click-contextmenu-for-different-node-types
function customMenu(node)
{

    if (node.original.is_dir) {
	var cm= { 'Show/Modify Access' : { 'label' : 'Show/Modify Access', 'action' : ShowEditEacl(node) },
		  'Share' : { 'label' : 'Share', 'action' : ShareFunc(node) },
		  'Create Symlink' : { 'label' : 'Create Symlink', 'action' : CreateSymlinkFunc(node) },
		  'CreateDir' : { 'label' : 'Create Directory', 'action' : CreateDirFunc(node) },
		  'StashFile' : { 'label' : 'Upload File', 'action' : StashFileFunc(node) },
		  'Root Here' : { 'label' : 'Root Here', 'submenu' : { 'Root Here' : { 'label' : 'Root Here', 'action' : RootHereFunc(node) },
								       'Show "Root Here" URL' : { 'label' : 'Show "Root Here" URL', 'action' : RootHereLinkFunc(node) } } },
		  'Download' : { 'label' : 'Download', 'submenu' : { 'Download (as zip)' : { 'label' : 'Download (as zip)', 'action' : DownloadDirFunc(node) },
								     'Show "Download (as zip)" URL' : { 'label' : 'Show "Download (as zip)" URL', 'action' : DownloadDirLinkFunc(node) } } },
		  'Refresh' : { 'label' : 'Refresh', 'action' : RefreshFunc(node) } };
	if (ALLOW_RENAME_DELETE) {
	    cm['Rename'] = { 'label' : 'Rename', 'action' : RenameFunc(node) };
	    cm['Delete'] = { 'label' : 'Delete', 'action' : DeleteFunc(node) };
	}
	if (node.original.path === 'data/nonclin') {
	    cm['Create Controlled Directory'] = { 'label' : 'Create Controlled Directory',
						  'action' : createControlledDirFunc(node) };
	}
	return(cm);
    } else {
	var cm= { 'Open/Download' : { 'label' : 'Open/Download', 'submenu' : { 'Open in Browser' : { 'label' : 'Open in Browser', 'action' : openFileNodeFunc(node) },
									       'Show "Open in Browser" URL' : { 'label' : 'Show "Open in Browser" URL', 'action' : openFileLinkFunc(node) },
									       'Download' : { 'label' : 'Download', 'action' : DownloadFileFunc(node) },
									       'Show "Download" URL' : { 'label' : 'Show "Download" URL', 'action' : DownloadLinkFunc(node) } } },
		  'Show/Modify Access' : { 'label' : 'Show/Modify Access', 'action' : ShowEditEacl(node) },
		  'Share' : { 'label' : 'Share', 'action' : ShareFunc(node) },
		  'Create Symlink' : { 'label' : 'Create Symlink', 'action' : CreateSymlinkFunc(node) } };

	if (ALLOW_RENAME_DELETE) {
	    cm['Rename'] = { 'label' : 'Rename', 'action' : RenameFunc(node) };
	    cm['Delete'] = { 'label' : 'Delete', 'action' : DeleteFunc(node) };
	}
	return(cm);
    }

}

function upLevel () {

   var rootArr = queryParams['root'];
   if (rootArr != null) {
       upLevelRoot = dirname(rootArr[0]);
       var relocUrl = 'index.html';
       var paramsArr = [];
       if (!isBlank(upLevelRoot)) {
	   paramsArr.push('root=' + upLevelRoot);
       }
       if (queryParams['fs']) { paramsArr.push('fs=' + queryParams['fs'][0]); }
       var paramsTxt = paramsArr.join("&");
       if (!isBlank(paramsTxt)) {
	   relocUrl += '?' + paramsTxt;
       }
       window.location = relocUrl;
   }
}

//Move node to have parent as its new parent node
//Do this at the server first via Ajax call,
//then update the tree to reflect the changes
//(if successful)
function doMoveNode(node, parent) {

    if (!parent.original.is_dir) { return; } //Can only move into a directory

    $('#spinner').show();

    var parent_path = parent.original.path;
    var parent_fn = parent.original.text;
    var node_path = node.original.path;
    var node_fn = node.original.text;

    var parent_path_prefix = dirname(parent_path);
    var node_path_prefix = dirname(node_path);

    var new_path = node_fn;
    if (!isBlank(parent_path)) { //not root
	new_path = parent_path + '/' + node_fn;
    }

    var data_vals = {'dir_path': node_path,
		     'new_path': new_path,
		     'a': 'move',
		     'stage': 'exec'};

    addCredsAndFs (data_vals);

    $.ajax({
	method: 'POST',
	url: simple_stash_service_url,
 
	// Tell jQuery we're expecting JSON
	dataType: 'json',

	'data': data_vals,
  
	// Work with the response
	success: function( response ) {
	    $('#spinner').hide();
	    if (!response.success) {
		alert('Error during move: ' + response.msg);
	    } else {

		$('#' + tree_div_id).jstree().delete_node(node); //delete the node from its old place in the tree

		$('#' + tree_div_id).jstree().refresh_node(parent); //and refresh its new parent so it shows there
		$('#' + tree_div_id).jstree().open_node(parent);

	    }
	},
	error: function (xhr, ajaxOptions, thrownError) {
	    $('#spinner').hide();
	    checkXhrFailure (xhr, thrownError, "Error During move");
	}
    });

}

function genRootStrWithLinks (root) {

    var rootParts = root.split('/');

    var rootLinks = [];
    for (var i=0; i<rootParts.length; i++) {
	var curRootParts = rootParts.slice(0,i+1);
	var curRoot = curRootParts.join("/");
	var root_here_url = window.location.origin + window.location.pathname + '?root=' + curRoot;
	var fsTxt = '';
	if (queryParams['fs']) { fsTxt = '&fs=' + queryParams['fs'][0]; }
	root_here_url += fsTxt;
	var curRootLink = '<a href="' + root_here_url + '">' + rootParts[i] + '</a>';
	rootLinks.push(curRootLink);
    }
    var rootStr = rootLinks.join("<b>/</b>");
    return(rootStr);

}

function addJiraAutocomplete (curInputName) {

    $( "#" + curInputName).autocomplete({
        source: function( request, response ) {

            $.ajax( {
		url: "/cgi-bin/stash_ui_release/searchJira_local.cgi",
                dataType: "json",
		data: {
		    'search_text': request.term
                },
                success: function( data ) {

		    var resultArr = data.results;

                    response( resultArr );
                }
            } );

        },
	autoFocus: true,
        minLength: 2,
        select: function( event, ui ) {
	    $(this).val(ui.item ? ui.item : " ");
        },
	change: function (event, ui) {
            if (!ui.item) {
                this.value = '';
	    }
        }

    });

}


function createControlledDirFunc(node) {

    var retFunc = function() {

	$('#createControlledDir_button').off('click');
	$("#createControlledDir_button").click(createControlledDirClickFunc(node));
	$('#createControlledDirPath').val('');
	addJiraAutocomplete ('createControlledDirPath');
	$("#createControlledDirModal").modal()
    }

    return(retFunc);

}

function createControlledDirClickFunc(node) {

    var retFunc = function() {
	if (isBlank($("#createControlledDirPath").val())) {
	    alert("Error: you did not choose a Jira Issue Key");
	    return;
	} else {
	    alert("Will create controlled dir: " + node.original.path + '/' + $("#createControlledDirPath").val());
	}
	$("#createControlledDirModal").modal('hide');
    }
    return retFunc;
}

function openFileNodeFunc (node) {

    var retFunc = function () {
	openFileNode(node);
    }

    return(retFunc);
}


function openFileNode (node) {

    if (!node.original.is_dir) {

	var params = { 'a': 'download_file',
		       'stage': 'exec',
		       'disposition': 'inline',
		       'file_path': node.original.path };

	addCredsAndFs (params);

	openWindowWithPostRequest('View File',simple_stash_service_url,params);
	return;
    }
}

//Got (and then modified slightly) here: https://stackoverflow.com/questions/3951768/window-open-and-pass-parameters-by-post-method
function openWindowWithPostRequest(winName,winURL,params) {
//  var winName='MyWindow';
//  var winURL='search.action';
//  var params = { 'param1' : '1','param2' :'2'};         
//    var windowoption='resizable=yes,height=600,width=800,location=0,menubar=0,scrollbars=1';
    var windowoption = '';
    var form = document.createElement("form");
    form.setAttribute("method", "post");
    form.setAttribute("action", winURL);
    form.setAttribute("target",winName);  
    for (var i in params) {
	if (params.hasOwnProperty(i)) {
	    var input = document.createElement('input');
	    input.type = 'hidden';
	    input.name = i;
	    input.value = params[i];
	    form.appendChild(input);
	}
    }        
    document.body.appendChild(form);                       
    window.open('', winName,windowoption);
    form.target = winName;
    form.submit();
    document.body.removeChild(form);           
}

function initJstree () {

   var root = '';
   var rootArr = queryParams['root'];
   if (rootArr != null) {
       root = rootArr[0];
        var upLevelButton = '<button onclick="upLevel();" type="button" class="btn btn-xs"><span title="Move up one level" class="glyphicon glyphicon-arrow-up" aria-hidden="true" style="font-size:10px;"></span></button>';
       $("#rootInfo").html("<b>ROOT:</b>&nbsp;" + genRootStrWithLinks (root) + '&nbsp;' + upLevelButton); // + '&nbsp;' + dirMenuButton
   }

   $('#' + tree_div_id).jstree({
    'core' : {
        'data' : function (obj, cb) {
	    var path_to_get = root;
	    if (obj && obj.original && !isBlank(obj.original.path)) {
		path_to_get = obj.original.path;
	    }
            getNextLevel(path_to_get,cb);
        },
	"check_callback" : function (op, node, parent, position, more) {
            switch (op) {
                case 'move_node':
                    if (more && more.core) {
			//See here: https://stackoverflow.com/questions/50769516/jstree-dnd-plugin-prevent-move-after-drop
			//and here: https://groups.google.com/forum/#!topic/jstree/bwZyny3eos4
                        // this is the condition when the user dropped,
                        // make a synchronous call to the server and
                        // return false if the server rejects the action.
			//Actually, better, always return false (so the move
			//doesn't happen right away), then do an Ajax call
			//to do the move at server, and if that succeeds
			//execute the actual move in the tree upon success
			doMoveNode(node, parent);
			return(false);
                    }
		    break;
		default: return(true); //allow all other actions
            }
        }
    },
    'contextmenu' : {
        'items' : customMenu
    },
    'plugins' : [
	"contextmenu", "dnd", "search",
	"types"
    ]
   }).bind("select_node.jstree", function (e, data) {

//       var evt =  window.event || e;
//       var button = evt.which || evt.button;
//       if( button != 1 && ( typeof button != "undefined")) { //don't refresh or open on right mouse click
//	   return false;
//       }
//       if (data.node.original.is_dir) {
//	   if ($('#' + tree_div_id).jstree().is_open(data.node)) {
//	       $('#' + tree_div_id).jstree().close_node(data.node);
//	   } else {
//	       if ($('#' + tree_div_id).jstree().is_loaded(data.node)) {
//		   $('#' + tree_div_id).jstree().open_node(data.node);
//	       } else {
//		   RefreshFunc(data.node)();
//	       }
//	   }
//       } else {
//	   openFileNode(data.node);
//       }

    }).bind("rename_node.jstree", function (e, data) {
	execRenameNode(data.node,data.text)
    }).bind("dblclick.jstree", function (event) {

	var tree = $(this).jstree();
//	var node = tree.get_node(event.target);
	var node = tree.get_node($(event.target).closest("li"));

	if (!node.original.is_dir) {
	    openFileNode(node);
	}

    });

//   jQuery.ajaxSetup({
//       beforeSend: function() {
//	   $('#spinner').show();
//       },
//       complete: function(){
//	   $('#spinner').hide();
//       },
//       success: function() {}
//   });
}

function isBlank(str) {
    return (!str || /^\s*$/.test(str));
}

function ssconfig () {

    var curSettings = getSettings();

    if (!isBlank(curSettings.privateKey)) {
	$("#ssconfig_sshPrivKey").val(curSettings.privateKey);
    }

    if (!isBlank(curSettings.password)) {
	$("#ssconfig_password").val(curSettings.password);
    }

    $('#ssconfig_Button').off('click');
    $("#ssconfig_Button").click(updateSshKey);
    $("#ssconfig_ClearButton").click(function() { $("#ssconfig_sshPrivKey").val(''); $("#ssconfig_password").val(''); });
    $("#ssconfigModal").modal();

}

function updateSshKey() {

    var curSettings = getSettings();
    var configSshKey = $("#ssconfig_sshPrivKey").val().trim();
    var configPassword = $("#ssconfig_password").val().trim();
    curSettings.privateKey = configSshKey;
    curSettings.password = btoa(configPassword);

    localStorage.setItem(localStorageName,JSON.stringify(curSettings));


    if (!isBlank(configSshKey)) {
	testSshKey();
    }

    if (!isBlank(configPassword)) {
	testPassword();
    }

    $("#ssconfigModal").modal('hide');

}

function getSettings () {
    var settingsJsonTxt = localStorage.getItem(localStorageName);
    var settings = {};
    if (!isBlank(settingsJsonTxt)) {
	settings = JSON.parse(settingsJsonTxt);
	if (!isBlank(settings.password)) { //decode the password
	    settings.password = atob(settings.password);
	}
    }

    return(settings);
}

$(document).ready(function(){
    docReadyFunc();
});

function docReadyFunc () {

   queryParams = getQueryParams();

   var postrd = queryParams['postrd'];
   if (postrd != null) {
       handlePostRD(postrd[0]);
   } else {

       initEditAclOnReady(['show-edit-acl','create-dir','stash-file']);

       //See here for how to set up dnd: https://stackoverflow.com/questions/19223352/jquery-ondrop-not-firing
       //This allows users to drag and drop file upload files into directory nodes:
       $(document).on('dragover', false).on('drop', function(event) {
	   event.preventDefault();
	   var nearestJstreeNodeDom = event.target.closest(".jstree-node");
	   if (nearestJstreeNodeDom) {
	       var jstreeNode = $('#' + tree_div_id).jstree().get_node(nearestJstreeNodeDom.id);
	       if (jstreeNode.original.is_dir) {
		   var draggedFiles = event.originalEvent.dataTransfer.files;
		   if (draggedFiles && (draggedFiles.length > 0)) {
		       var theUploadedFile = draggedFiles.item(0);
		       if (confirm("Do you want to upload file '" + theUploadedFile.name + "' to " + jstreeNode.original.path + "?")) {
			   doFileUpload (jstreeNode, theUploadedFile, 'u:' + current_user + ':rw', '', '');
		       }
		   }
	       }
	   }
       });


       $("#ssconfig").click(ssconfig);

       $('#share_with_users').tagsInput({
	   autocomplete_url: share_ac_func,
	   autocomplete: { 'select': share_ac_select_func },
	   defaultText:'Search...',
	   width: '100%'
       });

       var curSettings = getSettings();
       var cur_ssconfig_sshPrivKey = curSettings.privateKey;
       var cur_ssconfig_password = curSettings.password;
       if (!isBlank(cur_ssconfig_sshPrivKey)) {
	   testSshKey();
       }
       if (!isBlank(cur_ssconfig_password)) {
	   testPassword();
       }
       afterCheckSshKeyFunc();
   }
}


function handlePostRD (postrd_val) {

    if (postrd_val === 'download_file') {
	var rootArr = queryParams['root'];
	var viewfile = rootArr[0];
	var disposition = queryParams['disposition'];
	if (disposition != null) {
	    disposition = disposition[0];
	}
	if ((disposition != 'inline') &&
	    (disposition != 'attachment')) {
	    disposition = 'attachment';
	}

	var formArgs = { 'a': 'download_file',
			 'stage': 'exec',
			 'disposition': disposition,
			 'file_path': viewfile };
	if (!isBlank(queryParams['fs'])) { formArgs['fs'] = queryParams['fs'][0]; }
	doPostRD(formArgs);
    } else if (postrd_val === 'download_dir') {
	var rootArr = queryParams['root'];
	var download_dir = rootArr[0];
	var formArgs = { 'a': 'download_dir',
			 'stage': 'exec',
			 'dir_path': download_dir };
	if (!isBlank(queryParams['fs'])) { formArgs['fs'] = queryParams['fs'][0]; }
	doPostRD(formArgs);
    }

}

//POST redirect to simple_service.cgi, but with credentials
//added from browser local storage
function doPostRD (formArgs) {

    var url = simple_stash_service_url;

    var curSettings = getSettings();

    //See here for where I got this: https://stackoverflow.com/questions/8389646/send-post-data-on-redirect-with-javascript-jquery
    var formTxt = '<form id="post_rd_form" style="display:none" action="' + url + '" method="post">';
    if (!isBlank(curSettings.privateKey)) {
	formTxt += '<input type="hidden" name="user_sshkey" value="' + curSettings.privateKey + '" />';
    }
    if (!isBlank(curSettings.password)) {
	formTxt += '<input type="hidden" name="user_password" value="' + curSettings.password + '" />';
    }

    for (var curArg in formArgs) {
	var curArgVal = formArgs[curArg];
	formTxt += '<input type="hidden" name="' + curArg + '" value="' + curArgVal + '" />';
    }

    formTxt += '</form>';

    var form = $(formTxt);
    $('body').append(form);
    form.submit();
    $('#post_rd_form').remove();

}

function afterCheckSshKeyFunc () {

    var data_vals = {'a': 'get_current_user'};

    addCredsAndFs (data_vals);

    $.ajax({
	method: 'POST',
	url: simple_stash_service_url,
 
	// Tell jQuery we're expecting JSON
	dataType: 'json',

	'data': data_vals,
  
	// Work with the response
	success: function( response ) {
	    if (!response.success) {
		alert('Error during get_current_user: ' + response.msg);
	    } else {
		current_user = response.current_user;
	    }
	    initJstree();
	},
	error: function (xhr, ajaxOptions, thrownError) {
	    checkXhrFailure (xhr, thrownError, "Error During get_current_user");
	    initJstree();
	}
    });

}

/*
//Simple example context menu functions
//Use like this:
//	return { 'DirAction' : { 'label' : 'DirAction', 'action' : DirActionFunc(node) },
//		 'Show/Edit EACL' : { 'label' : 'Show/Edit EACL', 'action' : ShowEditEacl(node) },
//		 'Delete' : { 'label' : 'Delete', 'action' : DeleteFunc(node) } };
//    } else {
//	return { 'FileAction' : { 'label' : 'FileAction', 'action' : FileActionFunc(node) },
//		 'Download' : { 'label' : 'Download', 'action' : DownloadFileFunc(node) },
//		 'Show/Edit EACL' : { 'label' : 'Show/Edit EACL', 'action' : ShowEditEacl(node) },
//		 'Delete' : { 'label' : 'Delete', 'action' : DeleteFunc(node) } }

function DirActionFunc (node) {

    var retFunc = function () { var my_path = node.original.path; alert('Dir Path: ' + my_path); }

    return(retFunc);

}

function FileActionFunc (node) {

    var retFunc = function () { var my_path = node.original.path; alert('File Path: ' + my_path); }

    return(retFunc);

}


//.bind("move_node.jstree", function(e,data) { console.log(data); });

//		    $('#' + tree_div_id).jstree().refresh_node(node);
//		    $('#' + tree_div_id).jstree().open_node(node);

*/
